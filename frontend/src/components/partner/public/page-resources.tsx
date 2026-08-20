'use client';

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Palette, BookOpen, Cpu, HelpCircle, Code, Mail,
  ArrowRight, X, ExternalLink, Download, Copy, Check,
  Search, FileText, Layout, Wrench, Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePartnerStore } from '@/stores/partner-store';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';

type LucideIcon = typeof Palette;

type ResourceCategory = 'guides' | 'templates' | 'tools';

type FilterOption = 'all' | ResourceCategory;

interface Resource {
  title: string;
  description: string;
  icon: LucideIcon;
  category: ResourceCategory;
  categoryLabel: string;
  readTime: string;
  readMinutes: number;
  navigate?: string;
  summary: string;
  keyTakeaways: string[];
  actionLabel: string;
  actionIcon: 'download' | 'read';
  content: ResourceContent;
}

interface ContentBlock {
  type: 'paragraph' | 'heading' | 'code' | 'list' | 'tip' | 'color-swatch' | 'template';
  content: string;
  items?: string[];
  lang?: string;
  colors?: { name: string; value: string }[];
  templateData?: { subject: string; body: string };
}

interface ResourceContent {
  summary: string;
  blocks: ContentBlock[];
}

const categoryColors: Record<ResourceCategory, { border: string; bg: string; text: string }> = {
  guides: {
    border: 'border-l-amber-500/70',
    bg: 'bg-amber-500/5',
    text: 'text-amber-600 dark:text-amber-400',
  },
  templates: {
    border: 'border-l-violet-500/70',
    bg: 'bg-violet-500/5',
    text: 'text-violet-600 dark:text-violet-400',
  },
  tools: {
    border: 'border-l-emerald-500/70',
    bg: 'bg-emerald-500/5',
    text: 'text-emerald-600 dark:text-emerald-400',
  },
};

const categoryIcons: Record<FilterOption, LucideIcon> = {
  all: FileText,
  guides: BookOpen,
  templates: Layout,
  tools: Wrench,
};

const filterOptions: { value: FilterOption; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'guides', label: 'Guides' },
  { value: 'templates', label: 'Templates' },
  { value: 'tools', label: 'Tools' },
];

const resources: Resource[] = [
  {
    title: 'Brand Guidelines',
    description: 'Logo usage, colors, typography rules. Ensure your materials are on-brand.',
    icon: Palette,
    category: 'guides',
    categoryLabel: 'GUIDES',
    readTime: '5 min',
    readMinutes: 5,
    summary: 'Official guidelines for using RELIASTRA branding in your partner materials, presentations, and referral content. Covers logo usage, color palette, typography, and co-branding best practices.',
    keyTakeaways: [
      'Always maintain clear space around the logo equal to the checkmark height',
      'Use the reversed (white) logo version on dark backgrounds',
      'Keep RELIASTRA branding as accents — your brand identity stays primary',
      'Inter for body text, JetBrains Mono for code and labels',
    ],
    actionLabel: 'Download PDF',
    actionIcon: 'download',
    content: {
      summary: 'Official guidelines for using RELIASTRA branding in your partner materials, presentations, and referral content.',
      blocks: [
        {
          type: 'heading',
          content: 'Logo Usage',
        },
        {
          type: 'paragraph',
          content: 'The RELIASTRA logo should always appear with adequate clear space. Never stretch, rotate, or alter the logo. Use the provided SVG files for digital applications and high-resolution PNGs for print.',
        },
        {
          type: 'list',
          content: 'Minimum clear space equals the height of the checkmark inside the logo mark.',
          items: [
            'Always display the logo at its original proportions',
            'Minimum size: 24px width for digital, 0.5\" for print',
            'Never place the logo on busy backgrounds without a container',
            'The wordmark "RELIASTRA" uses Inter or a similar geometric sans-serif',
            'On dark backgrounds, use the reversed (white) version',
          ],
        },
        {
          type: 'heading',
          content: 'Color Palette',
        },
        {
          type: 'color-swatch',
          content: 'Primary colors used across RELIASTRA brand materials.',
          colors: [
            { name: 'Primary Black', value: '#09090B' },
            { name: 'Foreground', value: '#18181B' },
            { name: 'Muted', value: '#71717A' },
            { name: 'Border', value: '#E4E4E7' },
            { name: 'Background', value: '#FAFAFA' },
            { name: 'Accent Emerald', value: '#10B981' },
          ],
        },
        {
          type: 'heading',
          content: 'Typography',
        },
        {
          type: 'paragraph',
          content: 'RELIASTRA uses Inter as its primary typeface. For mono-spaced elements (labels, code, metadata), use JetBrains Mono. Headlines use semibold weight (600), body text uses regular (400).',
        },
        {
          type: 'tip',
          content: 'When creating referral materials, use the RELIASTRA brand colors as accents only. Your own brand identity should remain primary — the goal is subtle co-branding, not a full rebrand.',
        },
      ],
    },
  },
  {
    title: 'Referral Playbook',
    description: 'Strategies for effective referrals. Learn what works and what doesn\'t.',
    icon: BookOpen,
    category: 'guides',
    categoryLabel: 'GUIDES',
    readTime: '8 min',
    readMinutes: 8,
    summary: 'Battle-tested strategies from top-performing partners. Learn how to identify prospects, craft your pitch, and close referrals consistently without resorting to hard-sell tactics.',
    keyTakeaways: [
      'Lead with the problem RELIASTRA solves, not the commission',
      '1:1 email or Slack messages have the highest conversion rate',
      'Wait 5-7 days before following up, and never more than twice',
      'Personalized outreach converts at 15-25% vs 2% for generic messages',
    ],
    actionLabel: 'Read Full Guide',
    actionIcon: 'read',
    content: {
      summary: 'Battle-tested strategies from top-performing partners. Learn how to identify prospects, craft your pitch, and close referrals consistently.',
      blocks: [
        {
          type: 'heading',
          content: 'Identifying the Right Prospects',
        },
        {
          type: 'paragraph',
          content: 'The most effective referrals come from existing relationships. Look for people who have explicitly mentioned infrastructure reliability challenges, incident management pain, or compliance reporting needs.',
        },
        {
          type: 'list',
          content: 'Signs someone is a strong referral candidate:',
          items: [
            'They manage or oversee production infrastructure',
            'They\'ve expressed frustration with post-incident processes',
            'They need to produce evidence-based reliability reports',
            'Their team spends significant time on manual correlation',
            'They work in regulated industries (finance, healthcare, energy)',
          ],
        },
        {
          type: 'heading',
          content: 'The Referral Conversation',
        },
        {
          type: 'paragraph',
          content: 'Don\'t lead with the commission. Lead with the problem RELIASTRA solves. Frame it as: "I found something that addresses [specific pain point] we talked about." Let the product speak for itself — your role is to make the introduction.',
        },
        {
          type: 'tip',
          content: 'Avoid hard-selling. The best referrals feel like helpful recommendations between professionals, not sales pitches. Share your referral link naturally, ideally in a 1:1 context.',
        },
        {
          type: 'heading',
          content: 'Follow-Up Cadence',
        },
        {
          type: 'paragraph',
          content: 'After sharing your link, wait 5-7 days before following up. A simple "Did you get a chance to look at RELIASTRA? Happy to walk through it" is sufficient. Avoid more than two follow-ups — if they\'re not interested, move on.',
        },
        {
          type: 'heading',
          content: 'Channels That Work Best',
        },
        {
          type: 'list',
          content: 'Ranked by conversion rate from partner data:',
          items: [
            '1:1 email or Slack message (highest conversion)',
            'In-person conversation at events/meetings',
            'Technical blog post with contextual mention',
            'Community forum or Discord recommendation',
            'Social media post (lowest conversion, highest reach)',
          ],
        },
      ],
    },
  },
  {
    title: 'Email Templates',
    description: 'Pre-written email templates for outreach. Personalize and send.',
    icon: Mail,
    category: 'templates',
    categoryLabel: 'TEMPLATES',
    readTime: '3 min',
    readMinutes: 3,
    summary: 'Copy-ready email templates for different referral scenarios — from warm intros to community shares. Each template includes a subject line and body that you can customize in minutes.',
    keyTakeaways: [
      'Template 1: Direct introduction for warm contacts with infrastructure challenges',
      'Template 2: Technical community share for Slack, Discord, or mailing lists',
      'Template 3: Client recommendation for consultants and agencies',
      'Always personalize the bracketed sections for best results',
    ],
    actionLabel: 'Read Full Guide',
    actionIcon: 'read',
    content: {
      summary: 'Copy-ready email templates for different referral scenarios. Personalize the bracketed sections before sending.',
      blocks: [
        {
          type: 'heading',
          content: 'Template 1: Direct Introduction',
        },
        {
          type: 'template',
          content: 'Best for warm contacts who have expressed infrastructure challenges.',
          templateData: {
            subject: 'Found something for your incident management workflow',
            body: 'Hi [Name],\n\nFollowing up on our conversation about [specific pain point]. I\'ve been using a tool called RELIASTRA that handles exactly this — it tracks incidents across systems and produces the correlation reports you mentioned needing.\n\nWorth a look: [your referral link]\n\nHappy to share more about my experience with it if useful.\n\nBest,\n[Your name]',
          },
        },
        {
          type: 'heading',
          content: 'Template 2: Technical Community Share',
        },
        {
          type: 'template',
          content: 'Best for sharing in Slack communities, Discord servers, or email lists.',
          templateData: {
            subject: 'Tool recommendation: cross-system incident correlation',
            body: 'Hey everyone — wanted to share a tool I\'ve been using for incident tracking and cross-system correlation. RELIASTRA connects to your existing monitoring stack and builds dependency maps automatically.\n\nThe evidence-based reporting has been particularly useful for our compliance audits.\n\nIf you want to check it out: [your referral link]\n\nHappy to answer questions about my setup.',
          },
        },
        {
          type: 'heading',
          content: 'Template 3: Client Recommendation',
        },
        {
          type: 'template',
          content: 'Best for consultants and agencies recommending to clients.',
          templateData: {
            subject: 'Incident management recommendation for [Client Name]',
            body: 'Hi [Name],\n\nDuring our recent assessment, I identified an opportunity to improve your incident response workflow. I\'d recommend evaluating RELIASTRA — it provides the cross-system correlation and audit-ready reporting that aligns with your compliance requirements.\n\nYou can explore the platform here: [your referral link]\n\nI\'m happy to facilitate an introduction to their team if you\'d like.\n\nRegards,\n[Your name]',
          },
        },
        {
          type: 'tip',
          content: 'Always personalize the [bracketed] sections. Generic outreach converts at less than 2%, while personalized messages convert at 15-25%. The more specific you are about the prospect\'s situation, the better.',
        },
      ],
    },
  },
  {
    title: 'Social Media Kit',
    description: 'Ready-to-post social assets. Graphics, captions, and hashtag sets.',
    icon: Layout,
    category: 'templates',
    categoryLabel: 'TEMPLATES',
    readTime: '4 min',
    readMinutes: 4,
    summary: 'A complete social media toolkit with pre-designed post templates, caption frameworks, and curated hashtag sets for LinkedIn, Twitter/X, and technical communities.',
    keyTakeaways: [
      'Includes 6 post templates for different content angles (technical, business, personal)',
      'Pre-written caption frameworks with fill-in-the-blank customization',
      'Curated hashtag sets optimized for DevOps and SRE audiences',
      'Dos and don\'ts for partner social content that converts',
    ],
    actionLabel: 'Download PDF',
    actionIcon: 'download',
    content: {
      summary: 'A complete social media toolkit with pre-designed post templates, caption frameworks, and curated hashtag sets.',
      blocks: [
        {
          type: 'heading',
          content: 'Post Templates',
        },
        {
          type: 'paragraph',
          content: 'Each template includes a visual layout guide, suggested caption, and optimized posting times. The six angles cover: technical breakdown, results story, tool comparison, problem-solution, behind-the-scenes, and community discussion.',
        },
        {
          type: 'list',
          content: 'Template categories included:',
          items: [
            'Technical Breakdown — "Here\'s how I set up cross-system incident correlation"',
            'Results Story — "After 3 months with RELIASTRA, here\'s what changed"',
            'Tool Comparison — "Why we moved from spreadsheets to automated correlation"',
            'Problem-Solution — "The incident report that used to take 4 hours now takes 15 minutes"',
            'Behind-the-Scenes — "A look at how we handle post-incident reviews"',
            'Community Discussion — "What do you use for dependency mapping?"',
          ],
        },
        {
          type: 'heading',
          content: 'Caption Framework',
        },
        {
          type: 'paragraph',
          content: 'Use the Hook → Context → Proof → CTA structure. Start with a bold statement or question, provide context about your situation, share a specific result or metric, and end with a soft call-to-action to try RELIASTRA via your referral link.',
        },
        {
          type: 'tip',
          content: 'LinkedIn posts between 1,200-1,500 characters perform best for technical content. On Twitter/X, threads of 5-8 tweets outperform single posts. Always include a visual — posts with screenshots or diagrams get 2-3x more engagement.',
        },
      ],
    },
  },
  {
    title: 'Presentation Deck',
    description: 'Co-branded slide deck for client meetings and conference talks.',
    icon: Layout,
    category: 'templates',
    categoryLabel: 'TEMPLATES',
    readTime: '3 min',
    readMinutes: 3,
    summary: 'A polished, co-branded presentation deck template you can customize for client meetings, workshops, or conference talks. Includes speaker notes and data-backed slides.',
    keyTakeaways: [
      '12-slide deck covering the infrastructure reliability problem and RELIASTRA\'s solution',
      'Includes editable data slides with industry statistics you can localize',
      'Speaker notes provided for each slide with talking points',
      'Customizable partner attribution slide for your contact info',
    ],
    actionLabel: 'Download PDF',
    actionIcon: 'download',
    content: {
      summary: 'A polished, co-branded presentation deck template you can customize for client meetings, workshops, or conference talks.',
      blocks: [
        {
          type: 'heading',
          content: 'Deck Structure',
        },
        {
          type: 'list',
          content: 'The 12-slide deck follows this structure:',
          items: [
            'Title slide with your name and co-branding',
            'The reliability problem — industry context',
            'Why spreadsheets and manual processes break down',
            'Introducing RELIASTRA — the solution overview',
            'How it works: Track, Correlate, Prove',
            'Real-world impact — data from production environments',
            'Integration ecosystem — works with your existing stack',
            'Case study template — customize with your experience',
            'Partner program overview and benefits',
            'Getting started — next steps for the audience',
            'Q&A slide',
            'Partner attribution — your contact details',
          ],
        },
        {
          type: 'tip',
          content: 'When presenting, spend the most time on slides 4-7 (the solution and impact). Data slides resonate most with technical audiences. Save the partner program details for the Q&A or a follow-up conversation.',
        },
      ],
    },
  },
  {
    title: 'Tracking Dashboard Guide',
    description: 'Navigate your partner dashboard. Track referrals, earnings, and payouts.',
    icon: Cpu,
    category: 'tools',
    categoryLabel: 'TOOLS',
    readTime: '6 min',
    readMinutes: 6,
    summary: 'A walkthrough of your partner dashboard — how to read your metrics, track referral status, understand commission calculations, and manage payouts effectively.',
    keyTakeaways: [
      'Dashboard shows real-time referral status: pending, active, churned',
      'Commission is 30% of the subscriber\'s monthly plan price',
      'Payouts are available once your balance reaches $50 minimum',
      'Use the API for custom integrations with your own tools',
    ],
    actionLabel: 'Read Full Guide',
    actionIcon: 'read',
    content: {
      summary: 'A walkthrough of your partner dashboard.',
      blocks: [
        {
          type: 'heading',
          content: 'Dashboard Overview',
        },
        {
          type: 'paragraph',
          content: 'Your partner dashboard is the central hub for tracking all referral activity, commission earnings, and payout requests. It updates in real-time as your referrals progress through the signup and subscription flow.',
        },
        {
          type: 'heading',
          content: 'Key Metrics',
        },
        {
          type: 'list',
          content: 'The four primary metrics on your overview:',
          items: [
            'Total Earned — cumulative commission across all active referrals',
            'This Month — commission earned in the current billing period',
            'Active Customers — referrals with an active RELIASTRA subscription',
            'Payable — balance available for withdrawal (minimum $50)',
          ],
        },
        {
          type: 'heading',
          content: 'Referral Status Tracking',
        },
        {
          type: 'paragraph',
          content: 'Each referral moves through a lifecycle: Pending (clicked link, not yet signed up) → Trial (signed up, in free trial) → Active (paying subscriber) → Churned (cancelled subscription). You earn commission only on Active status referrals.',
        },
        {
          type: 'tip',
          content: 'Check your dashboard weekly to catch referrals stuck in Pending status. A gentle follow-up at the right time can convert a Pending referral into an Active one.',
        },
      ],
    },
  },
];

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.1,
    },
  },
};

const staggerChild = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: [0.25, 0.1, 0.25, 1] },
  },
};

// --- Resource detail sheet content ---
function ResourceDetail({ resource, onClose }: { resource: Resource; onClose: () => void }) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
    toast.success('Copied to clipboard');
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-border/60 px-6 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border/80">
              <resource.icon className="size-4 text-muted-foreground" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">{resource.title}</h2>
              <div className="mt-1 flex items-center gap-2">
                <span className={
                  `font-mono text-[10px] uppercase tracking-wider ${categoryColors[resource.category].text}`
                }>
                  {resource.categoryLabel}
                </span>
                <span className="text-muted-foreground/40">·</span>
                <span className="text-[11px] text-muted-foreground">{resource.readTime}</span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* Body - scrollable */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {resource.content.summary}
        </p>

        <div className="mt-8 space-y-8">
          {resource.content.blocks.map((block, i) => (
            <div key={i}>
              {block.type === 'heading' && (
                <h3 className="mb-3 text-sm font-semibold text-foreground">{block.content}</h3>
              )}

              {block.type === 'paragraph' && (
                <p className="text-sm leading-relaxed text-muted-foreground">{block.content}</p>
              )}

              {block.type === 'list' && (
                <div className="space-y-2">
                  {block.content && (
                    <p className="mb-2 text-sm text-muted-foreground">{block.content}</p>
                  )}
                  {block.items?.map((item, j) => (
                    <div key={j} className="flex gap-2.5">
                      <div className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-foreground/40" />
                      <p className="text-sm leading-relaxed text-muted-foreground">{item}</p>
                    </div>
                  ))}
                </div>
              )}

              {block.type === 'code' && (
                <div className="relative rounded-lg border border-border/60 bg-muted/30">
                  <div className="flex items-center justify-between border-b border-border/40 px-4 py-2">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      {block.lang || 'code'}
                    </span>
                    <button
                      onClick={() => handleCopy(block.content, `code-${i}`)}
                      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {copiedId === `code-${i}` ? (
                        <><Check className="size-3" /> Copied</>
                      ) : (
                        <><Copy className="size-3" /> Copy</>
                      )}
                    </button>
                  </div>
                  <pre className="overflow-x-auto p-4">
                    <code className="font-mono text-xs leading-relaxed text-foreground/80">
                      {block.content}
                    </code>
                  </pre>
                </div>
              )}

              {block.type === 'tip' && (
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-50/40 px-4 py-3 dark:bg-emerald-950/30">
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
                    Pro tip
                  </p>
                  <p className="text-sm leading-relaxed text-emerald-900/80 dark:text-emerald-100/80">{block.content}</p>
                </div>
              )}

              {block.type === 'color-swatch' && (
                <div>
                  {block.content && (
                    <p className="mb-3 text-sm text-muted-foreground">{block.content}</p>
                  )}
                  <div className="grid grid-cols-2 gap-2">
                    {block.colors?.map((color) => (
                      <div
                        key={color.name}
                        className="flex items-center gap-3 rounded-md border border-border/60 px-3 py-2.5"
                      >
                        <div
                          className="h-6 w-6 shrink-0 rounded border border-border/40"
                          style={{ backgroundColor: color.value }}
                        />
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-foreground">{color.name}</p>
                          <p className="font-mono text-[10px] text-muted-foreground">{color.value}</p>
                        </div>
                        <button
                          onClick={() => handleCopy(color.value, `color-${color.name}`)}
                          className="ml-auto shrink-0 rounded p-1 text-muted-foreground/50 transition-colors hover:text-foreground"
                          aria-label={`Copy ${color.value}`}
                        >
                          {copiedId === `color-${color.name}` ? (
                            <Check className="size-3" />
                          ) : (
                            <Copy className="size-3" />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {block.type === 'template' && block.templateData && (
                <div className="rounded-lg border border-border/60 bg-background">
                  <div className="flex items-center justify-between border-b border-border/40 px-4 py-2.5">
                    <span className="text-xs text-muted-foreground">{block.content}</span>
                    <button
                      onClick={() => handleCopy(`${block.templateData!.subject}\n\n${block.templateData!.body}`, `tpl-${i}`)}
                      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {copiedId === `tpl-${i}` ? (
                        <><Check className="size-3" /> Copied</>
                      ) : (
                        <><Copy className="size-3" /> Copy</>
                      )}
                    </button>
                  </div>
                  <div className="p-4">
                    <p className="mb-1.5">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                        Subject
                      </span>
                    </p>
                    <p className="mb-3 text-sm font-medium text-foreground">
                      {block.templateData.subject}
                    </p>
                    <p className="mb-1.5">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                        Body
                      </span>
                    </p>
                    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-muted-foreground">
                      {block.templateData.body}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-border/60 px-6 py-4">
        {resource.navigate ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              onClose();
              setTimeout(() => {
                usePartnerStore.getState().navigate(resource.navigate as any);
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }, 200);
            }}
            className="w-full gap-2"
          >
            View full FAQ page
            <ExternalLink className="size-3.5" />
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            className="w-full"
          >
            Close
          </Button>
        )}
      </div>
    </div>
  );
}

// --- Expandable resource card ---
function ResourceCard({
  resource,
  expanded,
  onToggle,
  onViewFull,
}: {
  resource: Resource;
  expanded: boolean;
  onToggle: () => void;
  onViewFull: () => void;
}) {
  const Icon = resource.icon;
  const colors = categoryColors[resource.category];

  return (
    <motion.div
      layout
      className={
        `rounded-lg border border-border/80 bg-background overflow-hidden transition-colors duration-200 hover:border-foreground/15 ${colors.border} border-l-[3px]`
      }
    >
      {/* Card header - always visible, clickable */}
      <button
        onClick={onToggle}
        className="w-full text-left p-5 sm:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3.5 min-w-0">
            <div className={
              `mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border/80 ${colors.bg}`
            }>
              <Icon className={`size-4 ${colors.text}`} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2.5 mb-1.5">
                <h3 className="text-sm font-semibold text-foreground truncate">
                  {resource.title}
                </h3>
                <span className={
                  `shrink-0 rounded border px-1.5 py-0.5 font-mono text-[9px] font-medium uppercase tracking-wider ${colors.bg} ${colors.text} border-current/20`
                }>
                  {resource.categoryLabel}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground line-clamp-2">
                {resource.description}
              </p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground/60">
              <Clock className="size-3" />
              {resource.readTime}
            </span>
            <motion.div
              animate={{ rotate: expanded ? 180 : 0 }}
              transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
              className="text-muted-foreground/50"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </motion.div>
          </div>
        </div>
      </button>

      {/* Expanded content */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-border/40 px-5 pb-5 pt-5 sm:px-6 sm:pb-6">
              {/* Summary */}
              <p className="text-sm leading-relaxed text-muted-foreground mb-4">
                {resource.summary}
              </p>

              {/* Key takeaways */}
              <div className="mb-5">
                <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Key takeaways
                </p>
                <ul className="space-y-1.5">
                  {resource.keyTakeaways.map((takeaway, i) => (
                    <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-foreground/30" />
                      {takeaway}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (resource.navigate) {
                      onViewFull();
                    } else {
                      onViewFull();
                    }
                  }}
                  className="gap-2 text-xs"
                >
                  {resource.actionIcon === 'download' ? (
                    <Download className="size-3.5" />
                  ) : (
                    <ArrowRight className="size-3.5" />
                  )}
                  {resource.actionLabel}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewFull();
                  }}
                  className="gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                >
                  View full content
                  <ExternalLink className="size-3" />
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function PageResources() {
  const navigate = usePartnerStore((s) => s.navigate);
  const [selectedResource, setSelectedResource] = useState<Resource | null>(null);
  const [activeFilter, setActiveFilter] = useState<FilterOption>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCard, setExpandedCard] = useState<string | null>(null);

  const filteredResources = useMemo(() => {
    return resources.filter((r) => {
      const matchesFilter = activeFilter === 'all' || r.category === activeFilter;
      const query = searchQuery.toLowerCase().trim();
      const matchesSearch = !query ||
        r.title.toLowerCase().includes(query) ||
        r.description.toLowerCase().includes(query) ||
        r.summary.toLowerCase().includes(query);
      return matchesFilter && matchesSearch;
    });
  }, [activeFilter, searchQuery]);

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="border-b border-border/60">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          >
            <p className="mb-4 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              RESOURCES
            </p>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Partner resources.
            </h1>
            <p className="mt-3 max-w-lg text-base text-muted-foreground">
              Everything you need to effectively refer customers to RELIASTRA.
            </p>
          </motion.div>
        </div>
      </div>

      {/* Filter bar + Search */}
      <div className="border-b border-border/40 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            {/* Filter tabs */}
            <div className="flex items-center gap-1">
              {filterOptions.map((opt) => {
                const FilterIcon = categoryIcons[opt.value];
                const isActive = activeFilter === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setActiveFilter(opt.value);
                      setExpandedCard(null);
                    }}
                    className={
                      `inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                        isActive
                          ? 'bg-foreground text-background'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                      }`
                    }
                  >
                    <FilterIcon className="size-3" />
                    {opt.label}
                  </button>
                );
              })}
            </div>

            {/* Search input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground/50" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setExpandedCard(null);
                }}
                placeholder="Search resources..."
                className="h-9 w-full rounded-md border border-border/60 bg-background pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground/50 outline-none transition-colors focus:border-border sm:w-64"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Resource cards list */}
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6 sm:py-14 lg:px-8">
        <AnimatePresence mode="wait">
          {filteredResources.length > 0 ? (
            <motion.div
              key={`${activeFilter}-${searchQuery}`}
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
              exit="hidden"
              className="space-y-3"
            >
              {filteredResources.map((resource) => (
                <motion.div key={resource.title} variants={staggerChild}>
                  <ResourceCard
                    resource={resource}
                    expanded={expandedCard === resource.title}
                    onToggle={() =>
                      setExpandedCard((prev) =>
                        prev === resource.title ? null : resource.title
                      )
                    }
                    onViewFull={() => setSelectedResource(resource)}
                  />
                </motion.div>
              ))}
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              className="py-16 text-center"
            >
              <p className="text-sm text-muted-foreground">
                No resources found matching your search.
              </p>
              <button
                onClick={() => {
                  setSearchQuery('');
                  setActiveFilter('all');
                }}
                className="mt-2 text-xs font-medium text-foreground underline-offset-4 hover:underline"
              >
                Clear filters
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Results count */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          className="mt-8 font-mono text-xs text-muted-foreground"
        >
          {filteredResources.length} resource{filteredResources.length !== 1 ? 's' : ''} available.
          More are added regularly — check back for updates.
        </motion.p>
      </div>

      <Separator className="mx-auto max-w-6xl" />

      {/* CTA Section */}
      <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          className="flex flex-col items-start gap-6 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
              Ready to start?
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Join the partner program and start earning today.
            </p>
          </div>
          <Button
            size="lg"
            onClick={() => {
              navigate('signup');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            className="shrink-0"
          >
            BECOME A PARTNER
            <ArrowRight className="ml-2 size-4" />
          </Button>
        </motion.div>
      </div>

      {/* Resource Detail Sheet */}
      <AnimatePresence>
        {selectedResource && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-50 bg-black/50"
              onClick={() => setSelectedResource(null)}
            />
            <motion.div
              initial={{ opacity: 0, x: '100%' }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="fixed inset-y-0 right-0 z-50 w-full max-w-lg border-l border-border/60 bg-background shadow-2xl sm:max-w-md"
              onClick={(e) => e.stopPropagation()}
            >
              <ResourceDetail
                resource={selectedResource}
                onClose={() => setSelectedResource(null)}
              />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
