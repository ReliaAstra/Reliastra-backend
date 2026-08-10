// Package objectstore defines the object storage abstraction used for
// evidence artifacts, exports and future raw observation archives.
//
// The interface is deliberately small (Put/Get/Delete/Stat/Exists) so that
// S3-compatible backends (AWS S3, MinIO, Ceph, GCS S3-interop) and local
// filesystem storage are interchangeable. PostgreSQL is the source of truth
// for metadata; object storage holds blobs.
package objectstore

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// Object is a stored blob.
type Object struct {
	Key          string
	Size         int64
	ContentType  string
	LastModified time.Time
}

// Store is the storage backend abstraction.
type Store interface {
	// Put stores data under key.
	Put(ctx context.Context, key string, r io.Reader, size int64, contentType string) error
	// Get fetches the object; caller must close the returned reader.
	Get(ctx context.Context, key string) (io.ReadCloser, error)
	// Delete removes an object (idempotent).
	Delete(ctx context.Context, key string) error
	// Stat returns object metadata; ErrNotFound when absent.
	Stat(ctx context.Context, key string) (*Object, error)
	// Exists reports whether the object exists.
	Exists(ctx context.Context, key string) (bool, error)
	// Name returns a human-readable backend name.
	Name() string
}

// ErrNotFound is returned by Stat/Get when the object is missing.
var ErrNotFound = fmt.Errorf("objectstore: object not found")

// S3 implements Store over any S3-compatible endpoint.
type S3 struct {
	client *minio.Client
	bucket string
	region string
	prefix string
	name   string
}

// NewS3 builds an S3-compatible store.
func NewS3(endpoint, bucket, region, accessKey, secretKey string, useSSL bool, prefix string) (*S3, error) {
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: useSSL,
		Region: region,
	})
	if err != nil {
		return nil, fmt.Errorf("objectstore: s3 client: %w", err)
	}
	return &S3{client: client, bucket: bucket, region: region, prefix: strings.TrimSuffix(prefix, "/"), name: "s3:" + endpoint}, nil
}

// EnsureBucket creates the bucket if missing.
func (s *S3) EnsureBucket(ctx context.Context) error {
	exists, err := s.client.BucketExists(ctx, s.bucket)
	if err != nil {
		return fmt.Errorf("objectstore: bucket check: %w", err)
	}
	if !exists {
		if err := s.client.MakeBucket(ctx, s.bucket, minio.MakeBucketOptions{Region: s.region}); err != nil {
			return fmt.Errorf("objectstore: make bucket: %w", err)
		}
	}
	return nil
}

func (s *S3) key(k string) string {
	if s.prefix == "" {
		return k
	}
	return s.prefix + "/" + k
}

// Put implements Store.
func (s *S3) Put(ctx context.Context, key string, r io.Reader, size int64, contentType string) error {
	_, err := s.client.PutObject(ctx, s.bucket, s.key(key), r, size, minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		return fmt.Errorf("objectstore: put %s: %w", key, err)
	}
	return nil
}

// Get implements Store.
func (s *S3) Get(ctx context.Context, key string) (io.ReadCloser, error) {
	obj, err := s.client.GetObject(ctx, s.bucket, s.key(key), minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("objectstore: get %s: %w", key, err)
	}
	if _, err := obj.Stat(); err != nil {
		obj.Close()
		return nil, ErrNotFound
	}
	return obj, nil
}

// Delete implements Store.
func (s *S3) Delete(ctx context.Context, key string) error {
	return s.client.RemoveObject(ctx, s.bucket, s.key(key), minio.RemoveObjectOptions{})
}

// Stat implements Store.
func (s *S3) Stat(ctx context.Context, key string) (*Object, error) {
	info, err := s.client.StatObject(ctx, s.bucket, s.key(key), minio.StatObjectOptions{})
	if err != nil {
		return nil, ErrNotFound
	}
	return &Object{Key: key, Size: info.Size, ContentType: info.ContentType, LastModified: info.LastModified}, nil
}

// Exists implements Store.
func (s *S3) Exists(ctx context.Context, key string) (bool, error) {
	_, err := s.Stat(ctx, key)
	if err == ErrNotFound {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

// Name implements Store.
func (s *S3) Name() string { return s.name }

// Filesystem implements Store on a local directory (development, small
// single-VPS deployments, and test emulation of object storage).
type Filesystem struct {
	root   string
	prefix string
}

// NewFilesystem builds a filesystem store rooted at root.
func NewFilesystem(root string, prefix string) (*Filesystem, error) {
	if err := os.MkdirAll(root, 0o750); err != nil {
		return nil, fmt.Errorf("objectstore: fs root: %w", err)
	}
	return &Filesystem{root: root, prefix: strings.TrimSuffix(prefix, "/")}, nil
}

func (f *Filesystem) path(key string) (string, error) {
	if f.prefix != "" {
		key = f.prefix + "/" + key
	}
	p := filepath.Join(f.root, filepath.FromSlash(key))
	// Guard against path traversal.
	rel, err := filepath.Rel(f.root, p)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", fmt.Errorf("objectstore: invalid key %q", key)
	}
	return p, nil
}

// Put implements Store.
func (f *Filesystem) Put(_ context.Context, key string, r io.Reader, _ int64, _ string) error {
	p, err := f.path(key)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o750); err != nil {
		return err
	}
	tmp := p + ".tmp"
	out, err := os.Create(tmp)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, r); err != nil {
		out.Close()
		os.Remove(tmp)
		return err
	}
	if err := out.Close(); err != nil {
		os.Remove(tmp)
		return err
	}
	return os.Rename(tmp, p) // atomic on POSIX
}

// Get implements Store.
func (f *Filesystem) Get(_ context.Context, key string) (io.ReadCloser, error) {
	p, err := f.path(key)
	if err != nil {
		return nil, err
	}
	fh, err := os.Open(p)
	if err != nil {
		return nil, ErrNotFound
	}
	return fh, nil
}

// Delete implements Store.
func (f *Filesystem) Delete(_ context.Context, key string) error {
	p, err := f.path(key)
	if err != nil {
		return err
	}
	return os.Remove(p) //nolint:errcheck // idempotent by design
}

// Stat implements Store.
func (f *Filesystem) Stat(_ context.Context, key string) (*Object, error) {
	p, err := f.path(key)
	if err != nil {
		return nil, err
	}
	st, err := os.Stat(p)
	if err != nil {
		return nil, ErrNotFound
	}
	return &Object{Key: key, Size: st.Size(), LastModified: st.ModTime()}, nil
}

// Exists implements Store.
func (f *Filesystem) Exists(ctx context.Context, key string) (bool, error) {
	_, err := f.Stat(ctx, key)
	if err == ErrNotFound {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

// Name implements Store.
func (f *Filesystem) Name() string { return "filesystem:" + f.root }
