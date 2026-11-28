from datetime import datetime

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .campaign_urls import build_campaign_url
from .content_forms import (
    ContentBriefForm,
    ContentCategoryForm,
    ContentIdeaForm,
    ContentItemForm,
    ContentRefreshForm,
    ContentTagForm,
    ContentTemplateForm,
)
from .content_marketing import build_content_context, build_content_detail_context
from .models import (
    ContentBrief,
    ContentCategory,
    ContentIdea,
    ContentRefreshTask,
    ContentTag,
    ContentTemplate,
    MarketingContent,
    SocialPost,
)
from .social import sync_post_tracking_urls
from .validators import sanitize_text


@staff_member_required
def content_marketing_dashboard(request):
    category_form = ContentCategoryForm()
    tag_form = ContentTagForm()

    if request.method == 'POST':
        intent = request.POST.get('intent')
        if intent == 'add_category':
            category_form = ContentCategoryForm(request.POST)
            if category_form.is_valid():
                category = category_form.save()
                messages.success(request, f'Category “{category.name}” added.')
                return redirect(f'{reverse("admin:growth-center-content")}?section=library')
            messages.error(request, 'Please correct the category errors.')
        elif intent == 'add_tag':
            tag_form = ContentTagForm(request.POST)
            if tag_form.is_valid():
                tag = tag_form.save()
                messages.success(request, f'Tag “{tag.name}” added.')
                return redirect(f'{reverse("admin:growth-center-content")}?section=library')
            messages.error(request, 'Please correct the tag errors.')
        else:
            messages.error(request, 'Unknown content action.')

    context = build_content_context(request, category_form=category_form, tag_form=tag_form)
    context = {**admin.site.each_context(request), **context}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'html': render_to_string(
                'admin/growth_center/content_marketing_content.html',
                context,
                request=request,
            ),
            'section': context['active_section'],
        })

    return render(request, 'admin/growth_center/content_marketing.html', context)


@staff_member_required
def content_item_editor(request, content_key=None):
    item = get_object_or_404(MarketingContent, content_key=content_key) if content_key else None

    if request.method == 'POST':
        form = ContentItemForm(request.POST, instance=item, user=request.user)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            form.save_m2m()
            messages.success(request, f'Content “{instance.title}” saved with status {instance.status}.')
            return redirect('admin:growth-center-content-detail', instance.content_key)
        messages.error(request, 'Please correct the highlighted content fields.')
    else:
        form = ContentItemForm(instance=item)
        template_key = request.GET.get('template')
        if template_key:
            template = ContentTemplate.objects.filter(template_key=template_key).first()
            if template:
                form.initial['brief'] = template.structure
                form.initial['heading_structure'] = template.headings
                form.initial['cta'] = template.cta
                form.initial['seo_notes'] = template.seo_checklist
                form.initial['content_type'] = template.content_type
        if request.GET.get('date'):
            form.initial['target_publication_date'] = request.GET.get('date')

    context = {
        'title': f'Edit {item.title}' if item else 'Create Content',
        'form': form,
        'item': item,
        'is_edit': bool(item),
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/content_editor.html', context)


@staff_member_required
def content_detail(request, content_key):
    item = get_object_or_404(
        MarketingContent.objects.select_related('campaign', 'category').prefetch_related('tags', 'social_posts'),
        content_key=content_key,
    )
    context = build_content_detail_context(item, request)
    context = {**admin.site.each_context(request), **context}
    return render(request, 'admin/growth_center/content_detail.html', context)


@staff_member_required
@require_POST
def content_action(request, content_key):
    item = get_object_or_404(MarketingContent, content_key=content_key)
    action = request.POST.get('action')

    if action == 'duplicate':
        fields = {
            field.name: getattr(item, field.name)
            for field in MarketingContent._meta.fields
            if field.name not in {'id', 'content_key', 'created_at', 'updated_at', 'created_by', 'published_at'}
        }
        fields['title'] = f'{item.title} (Copy)'
        fields['status'] = 'Draft'
        fields['publication_url'] = ''
        copy = MarketingContent.objects.create(**fields, created_by=request.user)
        copy.tags.set(item.tags.all())
        copy.social_posts.set(item.social_posts.all())
        messages.success(request, f'Duplicated content as “{copy.title}”.')
        return redirect('admin:growth-center-content-detail', copy.content_key)
    if action == 'delete':
        title = item.title
        item.delete()
        messages.success(request, f'Deleted content “{title}”.')
        return redirect(f'{reverse("admin:growth-center-content")}?section=library')
    if action == 'submit_review':
        if not item.body.strip():
            messages.error(request, 'Add body content before submitting for review.')
            return redirect('admin:growth-center-content-detail', item.content_key)
        item.status = 'In Review'
        item.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'“{item.title}” moved to In Review.')
    elif action == 'approve':
        item.status = 'Approved'
        item.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'“{item.title}” approved.')
    elif action == 'archive':
        item.status = 'Archived'
        item.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'“{item.title}” archived.')
    elif action == 'mark_published':
        messages.info(request, 'Open the content editor and confirm the publication URL to mark content published.')
        return redirect('admin:growth-center-content-edit', item.content_key)
    else:
        messages.error(request, 'Unknown content action.')
    return redirect('admin:growth-center-content-detail', item.content_key)


@staff_member_required
def content_idea_editor(request, idea_key=None):
    idea = get_object_or_404(ContentIdea, idea_key=idea_key) if idea_key else None
    if request.method == 'POST':
        form = ContentIdeaForm(request.POST, instance=idea)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Idea “{instance.title}” saved.')
            return redirect(f'{reverse("admin:growth-center-content")}?section=ideas')
        messages.error(request, 'Please correct the idea errors.')
    else:
        form = ContentIdeaForm(instance=idea)
    context = {
        'title': f'Edit idea: {idea.title}' if idea else 'Capture Content Idea',
        'form': form,
        'idea': idea,
        'is_edit': bool(idea),
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/content_idea_editor.html', context)


@staff_member_required
@require_POST
def content_idea_action(request, idea_key):
    idea = get_object_or_404(ContentIdea, idea_key=idea_key)
    action = request.POST.get('action')

    if action == 'delete':
        title = idea.title
        idea.delete()
        messages.success(request, f'Deleted idea “{title}”.')
        return redirect(f'{reverse("admin:growth-center-content")}?section=ideas')
    if action == 'convert':
        if idea.is_used:
            messages.error(request, 'This idea has already been converted into content.')
            return redirect(f'{reverse("admin:growth-center-content")}?section=ideas')
        keywords = [part.strip() for part in idea.potential_keywords.split(',') if part.strip()]
        item = MarketingContent.objects.create(
            title=idea.title,
            content_type=idea.content_type,
            description=idea.description,
            brief=idea.description,
            topic=idea.topic,
            category=idea.category,
            target_audience=idea.target_audience,
            primary_keyword=keywords[0][:120] if keywords else '',
            secondary_keywords=', '.join(keywords[1:])[:500],
            priority=idea.priority,
            status='Planned',
            created_by=request.user,
        )
        idea.is_used = True
        idea.used_at = timezone.now()
        idea.converted_content = item
        idea.save(update_fields=['is_used', 'used_at', 'converted_content', 'updated_at'])
        messages.success(request, f'Created content draft “{item.title}” from the idea.')
        return redirect('admin:growth-center-content-edit', item.content_key)
    if action == 'reopen':
        idea.is_used = False
        idea.used_at = None
        idea.converted_content = None
        idea.save(update_fields=['is_used', 'used_at', 'converted_content', 'updated_at'])
        messages.success(request, f'Idea “{idea.title}” is available again.')
    else:
        messages.error(request, 'Unknown idea action.')
    return redirect(f'{reverse("admin:growth-center-content")}?section=ideas')


@staff_member_required
def content_brief_editor(request, brief_key=None):
    brief = get_object_or_404(ContentBrief, brief_key=brief_key) if brief_key else None
    if request.method == 'POST':
        form = ContentBriefForm(request.POST, instance=brief)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Brief “{instance.working_title}” saved.')
            return redirect(f'{reverse("admin:growth-center-content")}?section=briefs')
        messages.error(request, 'Please correct the brief errors.')
    else:
        form = ContentBriefForm(instance=brief)
        template_key = request.GET.get('template')
        if template_key:
            template = ContentTemplate.objects.filter(template_key=template_key).first()
            if template:
                form.initial['suggested_headings'] = template.headings
                form.initial['outline'] = template.structure
                form.initial['cta'] = template.cta
                form.initial['notes'] = template.brief_fields
                form.initial['content_type'] = template.content_type
        if request.GET.get('content'):
            content = MarketingContent.objects.filter(content_key=request.GET['content']).first()
            if content:
                form.initial['content'] = content.pk
                form.initial['working_title'] = content.title
                form.initial['primary_keyword'] = content.primary_keyword
                form.initial['target_audience'] = content.target_audience
                form.initial['search_intent'] = content.search_intent
                form.initial['topic'] = content.topic
                form.initial['proposed_slug'] = content.slug
                form.initial['content_type'] = content.content_type
    context = {
        'title': f'Edit brief: {brief.working_title}' if brief else 'Create Content Brief',
        'form': form,
        'brief': brief,
        'is_edit': bool(brief),
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/content_brief_editor.html', context)


@staff_member_required
@require_POST
def content_brief_action(request, brief_key):
    brief = get_object_or_404(ContentBrief, brief_key=brief_key)
    action = request.POST.get('action')

    if action == 'delete':
        title = brief.working_title
        brief.delete()
        messages.success(request, f'Deleted brief “{title}”.')
        return redirect(f'{reverse("admin:growth-center-content")}?section=briefs')
    if action == 'duplicate':
        copy = ContentBrief.objects.create(
            working_title=f'{brief.working_title} (Copy)',
            content=brief.content,
            content_type=brief.content_type,
            objective=brief.objective,
            target_audience=brief.target_audience,
            audience_pain_points=brief.audience_pain_points,
            search_intent=brief.search_intent,
            primary_keyword=brief.primary_keyword,
            secondary_keywords=brief.secondary_keywords,
            topic=brief.topic,
            proposed_slug=brief.proposed_slug,
            suggested_headings=brief.suggested_headings,
            outline=brief.outline,
            questions_to_answer=brief.questions_to_answer,
            internal_links=brief.internal_links,
            external_references=brief.external_references,
            cta=brief.cta,
            desired_length=brief.desired_length,
            competitor_urls=brief.competitor_urls,
            notes=brief.notes,
            is_reusable=brief.is_reusable,
            created_by=request.user,
        )
        messages.success(request, f'Duplicated brief as “{copy.working_title}”.')
        return redirect('admin:growth-center-content-brief-edit', copy.brief_key)
    if action == 'toggle_reusable':
        brief.is_reusable = not brief.is_reusable
        brief.save(update_fields=['is_reusable', 'updated_at'])
        messages.success(request, f'Brief “{brief.working_title}” is now {"reusable" if brief.is_reusable else "single-use"}.')
    else:
        messages.error(request, 'Unknown brief action.')
    return redirect(f'{reverse("admin:growth-center-content")}?section=briefs')


@staff_member_required
def content_template_editor(request, template_key=None):
    template = get_object_or_404(ContentTemplate, template_key=template_key) if template_key else None
    if request.method == 'POST':
        form = ContentTemplateForm(request.POST, instance=template)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Template “{instance.name}” saved.')
            return redirect(f'{reverse("admin:growth-center-content")}?section=templates')
        messages.error(request, 'Please correct the template errors.')
    else:
        form = ContentTemplateForm(instance=template)
    context = {
        'title': f'Edit template: {template.name}' if template else 'Create Content Template',
        'form': form,
        'template': template,
        'is_edit': bool(template),
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/content_template_editor.html', context)


@staff_member_required
@require_POST
def content_template_action(request, template_key):
    template = get_object_or_404(ContentTemplate, template_key=template_key)
    action = request.POST.get('action')

    if action == 'delete':
        name = template.name
        template.delete()
        messages.success(request, f'Deleted template “{name}”.')
        return redirect(f'{reverse("admin:growth-center-content")}?section=templates')
    if action == 'duplicate':
        copy = ContentTemplate.objects.create(
            name=f'{template.name} (Copy)',
            content_type=template.content_type,
            structure=template.structure,
            headings=template.headings,
            brief_fields=template.brief_fields,
            cta=template.cta,
            seo_checklist=template.seo_checklist,
            notes=template.notes,
            created_by=request.user,
        )
        messages.success(request, f'Duplicated template as “{copy.name}”.')
        return redirect('admin:growth-center-content-template-edit', copy.template_key)
    else:
        messages.error(request, 'Unknown template action.')
    return redirect(f'{reverse("admin:growth-center-content")}?section=templates')


@staff_member_required
def content_refresh_editor(request, refresh_key=None):
    task = get_object_or_404(ContentRefreshTask, refresh_key=refresh_key) if refresh_key else None
    if request.method == 'POST':
        form = ContentRefreshForm(request.POST, instance=task)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Refresh task for “{instance.content.title}” saved.')
            return redirect(f'{reverse("admin:growth-center-content")}?section=refresh')
        messages.error(request, 'Please correct the refresh task errors.')
    else:
        form = ContentRefreshForm(instance=task)
        if request.GET.get('content'):
            content = MarketingContent.objects.filter(content_key=request.GET['content'], status='Published').first()
            if content:
                form.initial['content'] = content.pk
    context = {
        'title': f'Edit refresh task: {task.content.title}' if task else 'Schedule Content Refresh',
        'form': form,
        'task': task,
        'is_edit': bool(task),
    }
    context.update(admin.site.each_context(request))
    return render(request, 'admin/growth_center/content_refresh_editor.html', context)


@staff_member_required
@require_POST
def content_refresh_action(request, refresh_key):
    task = get_object_or_404(ContentRefreshTask, refresh_key=refresh_key)
    action = request.POST.get('action')

    if action == 'delete':
        title = task.content.title
        task.delete()
        messages.success(request, f'Deleted refresh task for “{title}”.')
        return redirect(f'{reverse("admin:growth-center-content")}?section=refresh')
    if action == 'complete':
        notes = sanitize_text(request.POST.get('notes'), 4000)
        if not notes:
            messages.error(request, 'Add refresh notes before completing the task.')
            return redirect('admin:growth-center-content-refresh-edit', task.refresh_key)
        task.status = 'Completed'
        task.completed_at = timezone.now()
        task.update_notes = notes
        task.save(update_fields=['status', 'completed_at', 'update_notes', 'updated_at'])
        messages.success(request, f'Refresh task for “{task.content.title}” completed.')
        return redirect(f'{reverse("admin:growth-center-content")}?section=refresh')
    if action == 'reopen':
        task.status = 'Pending'
        task.completed_at = None
        task.save(update_fields=['status', 'completed_at', 'updated_at'])
        messages.success(request, f'Refresh task for “{task.content.title}” reopened.')
    else:
        messages.error(request, 'Unknown refresh action.')
    return redirect(f'{reverse("admin:growth-center-content")}?section=refresh')


@staff_member_required
@require_POST
def content_social_promotion(request, content_key):
    item = get_object_or_404(MarketingContent, content_key=content_key)
    if not item.campaign_id:
        messages.error(request, 'Link a campaign before creating a social promotion draft.')
        return redirect('admin:growth-center-content-detail', item.content_key)
    destination = item.publication_url or item.canonical_url
    if not destination:
        messages.error(request, 'Add a publication URL before creating a social promotion draft.')
        return redirect('admin:growth-center-content-detail', item.content_key)

    url, error = build_campaign_url(
        destination,
        source='content-marketing',
        medium='social',
        campaign=item.campaign.utm_campaign,
        term='',
        content=item.content_key.lower()[:120],
    )
    if error:
        messages.error(request, error)
        return redirect('admin:growth-center-content-detail', item.content_key)

    existing = SocialPost.objects.filter(
        title=f'Promote: {item.title}',
        destination_url=url,
        content_items=item,
    ).exists()
    if existing:
        messages.info(request, 'A social promotion draft already exists for this content.')
        return redirect('admin:growth-center-content-detail', item.content_key)

    excerpt = sanitize_text(item.description or item.body, 500)
    post = SocialPost.objects.create(
        title=f'Promote: {item.title}',
        content=excerpt or item.title,
        content_type='link',
        campaign=item.campaign,
        destination_url=url,
        utm_source='content-marketing',
        utm_medium='social',
        utm_campaign=item.campaign.utm_campaign,
        utm_content=item.content_key.lower()[:120],
        status='Draft',
        created_by=request.user,
    )
    sync_post_tracking_urls(post)
    item.social_posts.add(post)
    messages.success(request, 'Created a social promotion draft. Select platforms in Social Media before scheduling.')
    return redirect('admin:growth-center-social-post-edit', post.post_key)


@staff_member_required
@require_POST
def content_calendar_reschedule(request):
    item = get_object_or_404(MarketingContent, content_key=request.POST.get('key', ''))
    raw_date = request.POST.get('date', '')
    try:
        new_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Enter a valid date.'}, status=400)
    if item.status == 'Published':
        return JsonResponse({'ok': False, 'error': 'Published content cannot be rescheduled.'}, status=400)
    item.target_publication_date = new_date
    if item.status in {'Idea', 'Planned', 'Brief Created'}:
        item.status = 'Scheduled'
    item.save(update_fields=['target_publication_date', 'status', 'updated_at'])
    return JsonResponse({
        'ok': True,
        'key': item.content_key,
        'date': new_date.isoformat(),
        'status': item.status,
    })
