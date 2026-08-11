FROM reliastra-api:local
CMD ["celery", "-A", "app.infrastructure.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "checks,evidence,notifications"]
