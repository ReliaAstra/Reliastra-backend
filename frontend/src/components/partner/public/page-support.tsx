'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, Loader2, CheckCircle2, MessageSquare, Mail, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { usePartnerStore } from '@/stores/partner-store';
import { toast } from 'sonner';

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const subjectOptions = [
  'General inquiry',
  'Commission question',
  'Payout issue',
  'Referral tracking',
  'Account access',
  'Partnership terms',
  'Other',
];

export function PageSupport() {
  const navigate = usePartnerStore((s) => s.navigate);
  const user = usePartnerStore((s) => s.user);

  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [customSubject, setCustomSubject] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFieldError(null);

    const finalSubject = subject === 'Other' ? customSubject : subject;

    if (!name.trim() || !email.trim() || !finalSubject.trim() || !message.trim()) {
      setFieldError('All fields are required.');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch('/api/support', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), email: email.trim(), subject: finalSubject.trim(), message: message.trim() }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Submission failed');
      }

      setSubmitted(true);
      toast.success('Support request submitted — we\'ll respond within 24 hours');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('reach') || msg.includes('fetch')) {
        setFieldError('Unable to reach RELIASTRA. Check your connection and try again.');
      } else {
        setFieldError(msg || 'Unable to submit your request. Please try again.');
        toast.error('Failed to submit — please try again');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-12 sm:py-16">
      <div className="w-full max-w-lg">
        <motion.div
          initial="hidden"
          animate="visible"
          className="rounded-lg border border-border/60 bg-background p-6 sm:p-8"
        >
          {/* Header */}
          <motion.div variants={fadeUp} custom={0} className="mb-8">
            <button
              onClick={() => navigate('home')}
              className="mb-6 inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              Back to Partner Network
            </button>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex items-center justify-center size-10 rounded-lg border border-border/60 bg-muted/30">
                <MessageSquare className="size-5 text-foreground" />
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                  Contact
                </p>
                <h1 className="text-xl font-semibold tracking-tight text-foreground">
                  Support
                </h1>
              </div>
            </div>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Have a question about the partner program, commissions, or your account?
              We typically respond within 24 hours.
            </p>
          </motion.div>

          {/* Success state */}
          {submitted ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="py-8 text-center"
            >
              <div className="mx-auto mb-5 flex items-center justify-center size-12 rounded-full border border-border/60 bg-muted/30">
                <CheckCircle2 className="size-6 text-foreground" />
              </div>
              <h2 className="text-lg font-semibold tracking-tight text-foreground mb-2">
                Request submitted
              </h2>
              <p className="text-sm text-muted-foreground mb-6 max-w-sm mx-auto leading-relaxed">
                Thank you for reaching out. Our partner support team will review
                your request and respond to <span className="font-mono text-xs text-foreground">{email}</span> within 24 hours.
              </p>
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <Button
                  variant="outline"
                  onClick={() => {
                    setSubmitted(false);
                    setMessage('');
                    setSubject('');
                    setCustomSubject('');
                  }}
                  className="text-sm"
                >
                  Send another
                </Button>
                <Button
                  variant="default"
                  onClick={() => navigate('home')}
                  className="text-sm"
                >
                  Back to Partner Network
                </Button>
              </div>
            </motion.div>
          ) : (
            <>
              {/* Error */}
              {fieldError && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mb-5 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-700 dark:text-red-400"
                >
                  {fieldError}
                </motion.div>
              )}

              {/* Form */}
              <motion.form variants={fadeUp} custom={1} onSubmit={handleSubmit} className="space-y-5">
                <div className="grid gap-5 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="support-name" className="text-xs font-mono uppercase tracking-wider">
                      Name
                    </Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/60" />
                      <Input
                        id="support-name"
                        placeholder="Your name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        autoComplete="name"
                        className="pl-9 font-mono text-sm"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="support-email" className="text-xs font-mono uppercase tracking-wider">
                      Email
                    </Label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/60" />
                      <Input
                        id="support-email"
                        type="email"
                        placeholder="you@company.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        autoComplete="email"
                        className="pl-9 font-mono text-sm"
                      />
                    </div>
                  </div>
                </div>

                <Separator />

                <div className="space-y-2.5">
                  <Label className="text-xs font-mono uppercase tracking-wider">
                    Subject
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    {subjectOptions.map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => setSubject(opt)}
                        className={`
                          rounded-md border px-3 py-1.5 text-xs font-mono transition-all duration-150
                          ${subject === opt
                            ? 'border-foreground/80 bg-muted/60 text-foreground'
                            : 'border-border/60 text-muted-foreground hover:border-foreground/30 hover:text-foreground'
                          }
                        `}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                  {subject === 'Other' && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      transition={{ duration: 0.2 }}
                    >
                      <Input
                        placeholder="Describe your subject"
                        value={customSubject}
                        onChange={(e) => setCustomSubject(e.target.value)}
                        className="font-mono text-sm mt-2"
                        autoFocus
                      />
                    </motion.div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="support-message" className="text-xs font-mono uppercase tracking-wider">
                    Message
                  </Label>
                  <Textarea
                    id="support-message"
                    placeholder="Describe your question or issue in detail..."
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={5}
                    className="font-mono text-sm resize-none"
                  />
                  <p className="text-[11px] text-muted-foreground text-right">
                    {message.length} characters
                  </p>
                </div>

                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    'Send Message'
                  )}
                </Button>
              </motion.form>

              {/* Response time note */}
              <motion.div variants={fadeUp} custom={2} className="mt-6 flex items-start gap-3 rounded-md bg-muted/30 border border-border/40 px-4 py-3">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-0.5 text-muted-foreground">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Average response time is under 24 hours. For urgent matters, include &quot;URGENT&quot; in your subject line.
                </p>
              </motion.div>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}
