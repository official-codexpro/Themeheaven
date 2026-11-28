CONVERSION_EVENT_TYPES = (
    ('cta_click', 'CTA Click'),
    ('form_submission', 'Form Submission'),
    ('newsletter_signup', 'Newsletter Signup'),
    ('contact_request', 'Contact Request'),
    ('lead_generated', 'Lead Generated'),
    ('download', 'Download'),
    ('external_link_click', 'External Link Click'),
    ('phone_click', 'Phone Click'),
    ('email_click', 'Email Click'),
    ('page_visit', 'Page Visit'),
    ('custom_event', 'Custom Event'),
)

GOAL_TYPES = (
    ('Page Visit', 'Page Visit'),
    ('CTA Click', 'CTA Click'),
    ('Form Submission', 'Form Submission'),
    ('Custom Event', 'Custom Event'),
    ('Download', 'Download'),
    ('External Link Click', 'External Link Click'),
)

GOAL_STATUSES = (
    ('Active', 'Active'),
    ('Inactive', 'Inactive'),
)

FUNNEL_STATUSES = (
    ('Active', 'Active'),
    ('Inactive', 'Inactive'),
)

FUNNEL_STEP_TYPES = (
    ('page_view', 'Page Visit'),
    ('conversion', 'Conversion Event'),
)

TRACKING_RULE_STATUSES = (
    ('Active', 'Active'),
    ('Inactive', 'Inactive'),
)

COST_PERIODS = (
    ('one_time', 'One-time'),
    ('daily', 'Per day'),
    ('weekly', 'Per week'),
    ('monthly', 'Per month'),
)

CONVERSION_SECTIONS = (
    ('overview', 'Overview'),
    ('events', 'Events'),
    ('goals', 'Goals'),
    ('funnels', 'Funnels'),
    ('reports', 'Reports'),
    ('setup', 'Tracking Setup'),
    ('debugger', 'Event Debugger'),
)

CONVERSION_SORTS = (
    ('events', 'Total Events'),
    ('visitors', 'Unique Visitors'),
    ('name', 'Event Name'),
    ('page', 'Page URL'),
    ('date', 'Date'),
    ('campaign', 'Campaign'),
    ('source', 'Source'),
)

REPORT_VIEWS = (
    ('events', 'By Event'),
    ('pages', 'By Page'),
    ('sources', 'By Source'),
    ('campaigns', 'By Campaign'),
    ('devices', 'By Device'),
    ('over_time', 'Over Time'),
    ('landing_pages', 'Top Landing Pages'),
)

PRIVACY_NOTE = (
    'Conversion events store only privacy-safe identifiers, event labels, page paths, '
    'and attribution copied from the existing Analytics session. No form payloads, '
    'passwords, payment details, or personal fields are recorded.'
)

REVENUE_NOTE = (
    'Revenue tracking is not connected, so revenue and ROI are not calculated. '
    'Cost per conversion and cost per lead use campaign cost data entered by staff.'
)
