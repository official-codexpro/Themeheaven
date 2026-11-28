CONTENT_TYPES = (
    ('Blog Post', 'Blog Post'),
    ('Landing Page', 'Landing Page'),
    ('Guide', 'Guide'),
    ('Tutorial', 'Tutorial'),
    ('Case Study', 'Case Study'),
    ('News / Update', 'News / Update'),
    ('Newsletter', 'Newsletter'),
    ('Social Content', 'Social Content'),
    ('Video', 'Video'),
    ('Other', 'Other'),
)

CONTENT_STATUSES = (
    ('Idea', 'Idea'),
    ('Planned', 'Planned'),
    ('Brief Created', 'Brief Created'),
    ('In Progress', 'In Progress'),
    ('Draft', 'Draft'),
    ('In Review', 'In Review'),
    ('Approved', 'Approved'),
    ('Scheduled', 'Scheduled'),
    ('Published', 'Published'),
    ('Archived', 'Archived'),
)

CONTENT_PRIORITIES = (
    ('Low', 'Low'),
    ('Medium', 'Medium'),
    ('High', 'High'),
    ('Urgent', 'Urgent'),
)

IDEA_SOURCES = (
    ('Manual', 'Manual'),
    ('Customer Questions', 'Customer Questions'),
    ('Competitor Research', 'Competitor Research'),
    ('Keyword Research', 'Keyword Research'),
    ('Social Media', 'Social Media'),
    ('Analytics Insights', 'Analytics Insights'),
    ('Other', 'Other'),
)

CONTENT_SECTIONS = (
    ('overview', 'Overview'),
    ('calendar', 'Content Calendar'),
    ('library', 'Content Library'),
    ('ideas', 'Ideas'),
    ('briefs', 'Content Briefs'),
    ('templates', 'Content Templates'),
    ('performance', 'Content Performance'),
    ('refresh', 'Content Refresh'),
)

CONTENT_CALENDAR_VIEWS = (
    ('month', 'Monthly'),
    ('week', 'Weekly'),
    ('day', 'Daily'),
    ('list', 'List'),
)

CONTENT_SORTS = (
    ('date', 'Publication Date'),
    ('created', 'Created Date'),
    ('title', 'Title'),
    ('status', 'Status'),
    ('priority', 'Priority'),
    ('visits', 'Visits'),
)

REFRESH_STATUSES = (
    ('Pending', 'Pending'),
    ('In Progress', 'In Progress'),
    ('Completed', 'Completed'),
    ('Cancelled', 'Cancelled'),
)

SEO_CHECKLIST = (
    ('primary_keyword', 'Primary keyword defined'),
    ('seo_title', 'SEO title added'),
    ('meta_description', 'Meta description added'),
    ('url_slug', 'URL slug optimized'),
    ('heading_structure', 'Heading structure checked'),
    ('internal_links', 'Internal links added'),
    ('image_alt_text', 'Image alt text added'),
    ('content_preview', 'Content preview reviewed'),
    ('cta', 'CTA added'),
)

PRIORITY_ORDER = {'Low': 0, 'Medium': 1, 'High': 2, 'Urgent': 3}

DEFAULT_CONTENT_TEMPLATES = (
    {
        'name': 'SEO Blog Post',
        'content_type': 'Blog Post',
        'structure': 'Hook, problem, step-by-step guidance, examples, FAQ, conclusion, CTA.',
        'headings': 'H1: Main topic\nH2: Why it matters\nH2: How to do it\nH2: Examples\nH2: FAQ\nH2: Next steps',
        'brief_fields': 'Objective, audience, primary keyword, search intent, outline, internal links.',
        'cta': 'Link to the relevant product, guide, or support page.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'How-To Guide',
        'content_type': 'Guide',
        'structure': 'Outcome, prerequisites, numbered steps, troubleshooting, next steps.',
        'headings': 'H1: How to achieve the outcome\nH2: Prerequisites\nH2: Step-by-step\nH2: Troubleshooting\nH2: Next steps',
        'brief_fields': 'Audience pain points, questions to answer, tools required, CTA.',
        'cta': 'Invite the reader to explore the related product or contact support.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'Tutorial',
        'content_type': 'Tutorial',
        'structure': 'Goal, setup, walkthrough, common mistakes, recap.',
        'headings': 'H1: Tutorial title\nH2: Goal\nH2: Setup\nH2: Walkthrough\nH2: Common mistakes\nH2: Recap',
        'brief_fields': 'Skill level, required assets, screenshots, code or examples, CTA.',
        'cta': 'Link to the related documentation or product page.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'Case Study',
        'content_type': 'Case Study',
        'structure': 'Challenge, approach, implementation, results, lessons learned.',
        'headings': 'H1: Customer or project outcome\nH2: Challenge\nH2: Approach\nH2: Implementation\nH2: Results\nH2: Lessons',
        'brief_fields': 'Subject, approved facts, quotes, metrics source, permission notes, CTA.',
        'cta': 'Invite readers to request a similar solution.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'Product/Feature Announcement',
        'content_type': 'News / Update',
        'structure': 'Announcement, what changed, who benefits, how to use it, availability.',
        'headings': 'H1: Announcement title\nH2: What changed\nH2: Who it helps\nH2: How to use it\nH2: Availability',
        'brief_fields': 'Feature facts, audience, launch date, screenshots, support links, CTA.',
        'cta': 'Send readers to the product detail or demo.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'Comparison Article',
        'content_type': 'Blog Post',
        'structure': 'Criteria, side-by-side comparison, use cases, recommendation, FAQ.',
        'headings': 'H1: Comparison title\nH2: Criteria\nH2: Option A\nH2: Option B\nH2: Recommendation\nH2: FAQ',
        'brief_fields': 'Verified comparison criteria, sources, audience, recommendation, CTA.',
        'cta': 'Guide readers to the most relevant product or support resource.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'FAQ Article',
        'content_type': 'Blog Post',
        'structure': 'Short introduction, grouped questions, concise answers, related resources.',
        'headings': 'H1: FAQ title\nH2: Topic group\nH3: Question\nH2: Related resources',
        'brief_fields': 'Customer questions, verified answers, internal links, CTA.',
        'cta': 'Direct readers to support or the relevant product.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'Landing Page',
        'content_type': 'Landing Page',
        'structure': 'Hero, benefits, proof, features, FAQs, final CTA.',
        'headings': 'H1: Primary promise\nH2: Benefits\nH2: Features\nH2: Proof\nH2: FAQ\nH2: Get started',
        'brief_fields': 'Audience, value proposition, proof points, form or destination, CTA.',
        'cta': 'Use one primary conversion action repeated in the hero and footer.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
    {
        'name': 'Newsletter',
        'content_type': 'Newsletter',
        'structure': 'Subject line, opening, top stories, featured resource, closing CTA.',
        'headings': 'Subject: Newsletter subject\nH2: Opening\nH2: Top stories\nH2: Featured resource\nH2: Closing',
        'brief_fields': 'Audience segment, stories, links, send date, CTA.',
        'cta': 'Include one primary link and one secondary resource.',
        'seo_checklist': 'Keyword, title, description, slug, headings, internal links, alt text, preview, CTA.',
    },
)
