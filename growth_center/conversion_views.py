from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse

from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from .conversion import (
    build_conversion_context,
    build_event_detail_context,
    record_conversion_from_token,
)
from .conversion_forms import (
    CampaignCostForm,
    ConversionFunnelForm,
    ConversionGoalForm,
    TrackingRuleForm,
    funnel_step_formset,
)
from .models import CampaignCost, ConversionEvent, ConversionFunnel, ConversionGoal, TrackingRule


@staff_member_required
def conversion_dashboard(request):
    context = build_conversion_context(request)
    context = {**admin.site.each_context(request), **context}

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'html': render_to_string(
                'admin/growth_center/conversion_content.html',
                context,
                request=request,
            ),
            'section': context['active_section'],
        })

    return render(request, 'admin/growth_center/conversion.html', context)


@staff_member_required
def conversion_goal_editor(request, goal_key=None):
    goal = get_object_or_404(ConversionGoal, goal_key=goal_key) if goal_key else None
    if request.method == 'POST':
        form = ConversionGoalForm(request.POST, instance=goal)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Goal “{instance.name}” saved successfully.')
            return redirect(f'{reverse("admin:growth-center-conversion")}?section=goals')
        messages.error(request, 'Please correct the highlighted goal fields.')
    else:
        form = ConversionGoalForm(instance=goal)
    context = {
        **admin.site.each_context(request),
        'title': f'Edit {goal.name}' if goal else 'Create Goal',
        'form': form,
        'goal': goal,
        'is_edit': bool(goal),
    }
    return render(request, 'admin/growth_center/conversion_goal_editor.html', context)


@staff_member_required
@require_POST
def conversion_goal_action(request, goal_key):
    goal = get_object_or_404(ConversionGoal, goal_key=goal_key)
    action = request.POST.get('action')
    if action == 'toggle':
        goal.status = 'Inactive' if goal.status == 'Active' else 'Active'
        goal.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Goal “{goal.name}” is now {goal.status.lower()}.')
    elif action == 'delete':
        name = goal.name
        goal.delete()
        messages.success(request, f'Goal “{name}” deleted.')
    else:
        messages.error(request, 'Unknown goal action.')
    return redirect(f'{reverse("admin:growth-center-conversion")}?section=goals')


@staff_member_required
def conversion_funnel_editor(request, funnel_key=None):
    funnel = get_object_or_404(ConversionFunnel, funnel_key=funnel_key) if funnel_key else None
    if request.method == 'POST':
        form = ConversionFunnelForm(request.POST, instance=funnel)
        formset = funnel_step_formset(request.POST, instance=funnel)
        if form.is_valid() and formset.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            steps = formset.save(commit=False)
            for step in steps:
                step.funnel = instance
                step.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            messages.success(request, f'Funnel “{instance.name}” saved successfully.')
            return redirect(f'{reverse("admin:growth-center-conversion")}?section=funnels')
        messages.error(request, 'Please correct the highlighted funnel fields.')
    else:
        form = ConversionFunnelForm(instance=funnel)
        formset = funnel_step_formset(instance=funnel)
    context = {
        **admin.site.each_context(request),
        'title': f'Edit {funnel.name}' if funnel else 'Create Funnel',
        'form': form,
        'formset': formset,
        'funnel': funnel,
        'is_edit': bool(funnel),
    }
    return render(request, 'admin/growth_center/conversion_funnel_editor.html', context)


@staff_member_required
@require_POST
def conversion_funnel_action(request, funnel_key):
    funnel = get_object_or_404(ConversionFunnel, funnel_key=funnel_key)
    action = request.POST.get('action')
    if action == 'toggle':
        funnel.status = 'Inactive' if funnel.status == 'Active' else 'Active'
        funnel.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Funnel “{funnel.name}” is now {funnel.status.lower()}.')
    elif action == 'delete':
        name = funnel.name
        funnel.delete()
        messages.success(request, f'Funnel “{name}” deleted.')
    else:
        messages.error(request, 'Unknown funnel action.')
    return redirect(f'{reverse("admin:growth-center-conversion")}?section=funnels')


@staff_member_required
def conversion_rule_editor(request, rule_id=None):
    rule = get_object_or_404(TrackingRule, pk=rule_id) if rule_id else None
    if request.method == 'POST':
        form = TrackingRuleForm(request.POST, instance=rule)
        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.pk:
                instance.created_by = request.user
            instance.save()
            messages.success(request, f'Tracking rule “{instance.name}” saved successfully.')
            return redirect(f'{reverse("admin:growth-center-conversion")}?section=setup')
        messages.error(request, 'Please correct the highlighted tracking rule fields.')
    else:
        form = TrackingRuleForm(instance=rule)
    context = {
        **admin.site.each_context(request),
        'title': f'Edit {rule.name}' if rule else 'Create Tracking Rule',
        'form': form,
        'rule': rule,
        'is_edit': bool(rule),
    }
    return render(request, 'admin/growth_center/conversion_rule_editor.html', context)


@staff_member_required
@require_POST
def conversion_rule_action(request, rule_id):
    rule = get_object_or_404(TrackingRule, pk=rule_id)
    action = request.POST.get('action')
    if action == 'toggle':
        rule.status = 'Inactive' if rule.status == 'Active' else 'Active'
        rule.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Rule “{rule.name}” is now {rule.status.lower()}.')
    elif action == 'delete':
        name = rule.name
        rule.delete()
        messages.success(request, f'Rule “{name}” deleted.')
    else:
        messages.error(request, 'Unknown tracking rule action.')
    return redirect(f'{reverse("admin:growth-center-conversion")}?section=setup')


@staff_member_required
def conversion_cost_editor(request, cost_id=None):
    cost = get_object_or_404(CampaignCost, pk=cost_id) if cost_id else None
    if request.method == 'POST':
        form = CampaignCostForm(request.POST, instance=cost)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.updated_by = request.user
            instance.save()
            messages.success(request, 'Campaign cost saved successfully.')
            return redirect(f'{reverse("admin:growth-center-conversion")}?section=reports')
        messages.error(request, 'Please correct the highlighted cost fields.')
    else:
        form = CampaignCostForm(instance=cost)
    context = {
        **admin.site.each_context(request),
        'title': f'Edit cost for {cost.campaign.name}' if cost else 'Add Campaign Cost',
        'form': form,
        'cost': cost,
        'is_edit': bool(cost),
    }
    return render(request, 'admin/growth_center/conversion_cost_editor.html', context)


@staff_member_required
@require_POST
def conversion_cost_action(request, cost_id):
    cost = get_object_or_404(CampaignCost, pk=cost_id)
    action = request.POST.get('action')
    if action == 'delete':
        cost.delete()
        messages.success(request, 'Campaign cost deleted.')
    else:
        messages.error(request, 'Unknown campaign cost action.')
    return redirect(f'{reverse("admin:growth-center-conversion")}?section=reports')


@staff_member_required
def conversion_event_detail(request, event_key):
    event = get_object_or_404(
        ConversionEvent.objects.select_related('goal', 'session', 'visitor'),
        event_key=event_key,
    )
    context = build_event_detail_context(event, request)
    context = {**admin.site.each_context(request), **context}
    return render(request, 'admin/growth_center/conversion_event_detail.html', context)


@require_POST
def analytics_conversion(request):
    event = record_conversion_from_token(request)
    if not event:
        return HttpResponse(status=204)
    return JsonResponse({'ok': True, 'event_key': event.event_key})
