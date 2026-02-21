"""
Admin configuration for the agents app.

Provides admin interfaces for Agent, Category, and AgentSubmission models.
"""

import csv
import json
from datetime import datetime
from urllib.parse import urljoin

from django.contrib import admin
from django.db import models, transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.contrib import messages

from aiagents_directory.agents.models import (
    Agent,
    AgentSubmission,
    Category,
    Feature,
    Screenshot,
    SubmissionStatus,
    UseCase,
)
from aiagents_directory.agents.constants import AgentStatus
from aiagents_directory.auto_directory.services import DuplicateAgentError, EnrichmentService, ReviewService
from aiagents_directory.auto_directory.tasks import enrich_agent_task, enrich_submission_task


def pretty_json_html(data: dict | None, max_height: str = "400px") -> str:
    """
    Render a dict as pretty, syntax-highlighted JSON in a scrollable container.
    
    SECURITY: All user data is escaped before rendering.
    
    Args:
        data: Dictionary to render
        max_height: CSS max-height for the container (MUST be a safe CSS value like "400px")
        
    Returns:
        HTML string with styled JSON
    """
    if not data:
        return '<span style="color: #9ca3af;">—</span>'
    
    # Validate max_height to prevent CSS injection (defense in depth)
    import re
    if not re.match(r'^\d+px$', max_height):
        max_height = "400px"  # Default to safe value
    
    try:
        formatted = json.dumps(data, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        formatted = str(data)
    
    # Simple syntax highlighting
    # Strings in green, numbers in blue, booleans in purple, null in gray
    
    # Escape ALL HTML special characters (order matters: & first)
    formatted = (
        formatted
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
    
    # Highlight patterns (order matters!)
    # Note: After escaping, quotes are &quot; so we match the escaped version
    formatted = re.sub(r'&quot;([^&]+)&quot;:', r'<span style="color:#059669;">&quot;\1&quot;</span>:', formatted)  # Keys
    formatted = re.sub(r': &quot;([^&]*)&quot;', r': <span style="color:#0ea5e9;">&quot;\1&quot;</span>', formatted)  # String values
    formatted = re.sub(r': (\d+\.?\d*)', r': <span style="color:#8b5cf6;">\1</span>', formatted)  # Numbers
    formatted = re.sub(r': (true|false)', r': <span style="color:#d946ef;">\1</span>', formatted)  # Booleans
    formatted = re.sub(r': (null)', r': <span style="color:#9ca3af;">\1</span>', formatted)  # Null
    
    return f'''
    <div style="
        background: #1e293b;
        color: #e2e8f0;
        padding: 12px;
        border-radius: 8px;
        font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
        font-size: 12px;
        line-height: 1.5;
        max-height: {max_height};
        overflow: auto;
        white-space: pre;
    ">{formatted}</div>
    '''


class ScreenshotInline(admin.TabularInline):
    model = Screenshot
    extra = 1


class FeatureInline(admin.TabularInline):
    model = Feature
    extra = 1
    verbose_name = "Feature"
    verbose_name_plural = "Features"
    fields = ["name"]


class UseCaseInline(admin.TabularInline):
    model = UseCase
    extra = 1
    verbose_name = "Use Case"
    verbose_name_plural = "Use Cases"
    fields = ["name"]


def export_agents_to_csv(
    modeladmin: admin.ModelAdmin, request: HttpRequest, queryset: QuerySet
) -> HttpResponse:
    """Bulk action to export selected agents with all their data."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="agents_export_{timestamp}.csv"'},
    )

    writer = csv.writer(response)
    headers = [
        "id", "name", "slug", "short_description", "description",
        "website", "logo_url", "categories", "order", "featured",
        "created_at", "updated_at", "screenshot_urls",
    ]
    writer.writerow(headers)

    base_url = request.build_absolute_uri("/")[:-1]

    for agent in queryset:
        categories = ",".join(agent.categories.values_list("name", flat=True))
        logo_url = urljoin(base_url, agent.logo.url) if agent.logo else ""
        screenshot_urls = ",".join(
            urljoin(base_url, screenshot.image.url)
            for screenshot in agent.screenshots.all()
        )

        row = [
            agent.id,
            agent.name,
            agent.slug,
            agent.short_description,
            agent.description,
            agent.website,
            logo_url,
            categories,
            agent.order,
            agent.featured,
            agent.created_at.isoformat(),
            agent.updated_at.isoformat(),
            screenshot_urls,
        ]
        writer.writerow(row)

    return response


export_agents_to_csv.short_description = "Export selected agents to CSV"


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = [
        "name", "status", "get_categories", "short_description",
        "website", "pricing_model", "industry",
    ]
    list_filter = [
        "status", "categories", "pricing_model", "industry",
        "is_open_source", "featured",
    ]
    search_fields = ["name", "short_description", "description"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ScreenshotInline, FeatureInline, UseCaseInline]
    filter_horizontal = ["categories"]
    actions = [export_agents_to_csv, "enrich_selected_agents"]
    fieldsets = (
        (None, {
            "fields": ("name", "slug", "status", "short_description", "description", "website", "logo")
        }),
        ("Categorization", {
            "fields": ("categories", "industry")
        }),
        ("Display Options", {
            "fields": ("order", "featured")
        }),
        ("Agent Details", {
            "fields": ("is_open_source", "pricing_model")
        }),
        ("Social & Media", {
            "fields": ("twitter_url", "linkedin_url", "demo_video_url")
        }),
    )

    @admin.display(description="Categories")
    def get_categories(self, obj: Agent) -> str:
        return ", ".join([category.name for category in obj.categories.all()])

    def get_actions(self, request: HttpRequest):
        """Remove delete action from the bulk actions list."""
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    @admin.action(description="🔄 Enrich selected agents")
    def enrich_selected_agents(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Enrich selected agents with data from their websites."""
        count = 0
        for agent in queryset:
            if not agent.website:
                messages.warning(request, f"Skipped {agent.name}: No website URL")
                continue
            
            # Queue the enrichment task
            enrich_agent_task.delay(agent.id)
            count += 1
        
        if count > 0:
            messages.success(
                request,
                f"Queued enrichment for {count} agent(s). Check Enrichment Logs for results."
            )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:agent_id>/enrich/",
                self.admin_site.admin_view(self.enrich_single_agent),
                name="agent-enrich",
            ),
        ]
        return custom_urls + urls

    def enrich_single_agent(self, request: HttpRequest, agent_id: int):
        """Enrich a single agent immediately (synchronous)."""
        agent = self.get_object(request, agent_id)
        
        if not agent.website:
            messages.warning(
                request, f"Cannot enrich: No website URL provided for {agent.name}"
            )
            return redirect("admin:agents_agent_change", agent_id)

        try:
            service = EnrichmentService()
            log = service.enrich_agent(agent, user=request.user)
            
            if log.success:
                messages.success(
                    request,
                    f"✅ Enriched {agent.name}. Updated: {', '.join(log.applied_fields) or 'no changes'}"
                )
            else:
                messages.error(
                    request,
                    f"❌ Enrichment failed for {agent.name}: {log.error_message}"
                )
        except Exception as e:
            messages.error(request, f"Enrichment error: {str(e)}")

        return redirect("admin:agents_agent_change", agent_id)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_enrich_button"] = True
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj and not add:
            context.update({
                "enrich_button": format_html(
                    '<a class="button default" href="{}">{}</a>',
                    reverse("admin:agent-enrich", args=[obj.pk]),
                    _("🔄 Enrich Agent")
                ),
            })
        return super().render_change_form(request, context, add, change, form_url, obj)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "agent_count"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]

    @admin.display(description="Agents")
    def agent_count(self, obj: Category) -> int:
        return obj.agents.count()


# ─────────────────────────────────────────────────────────────
# Custom Filters for AgentSubmission
# ─────────────────────────────────────────────────────────────

class EnrichmentStatusFilter(admin.SimpleListFilter):
    """Filter by enrichment status."""
    title = "enrichment"
    parameter_name = "enrichment"

    def lookups(self, request, model_admin):
        return [
            ("enriched", "✓ Enriched"),
            ("not_enriched", "✗ Not Enriched"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "enriched":
            return queryset.filter(enrichment_data__isnull=False)
        if self.value() == "not_enriched":
            return queryset.filter(enrichment_data__isnull=True)
        return queryset


class AIReviewStatusFilter(admin.SimpleListFilter):
    """Filter by AI review status and decision."""
    title = "AI review"
    parameter_name = "ai_review"

    def lookups(self, request, model_admin):
        return [
            ("reviewed", "✓ AI Reviewed"),
            ("not_reviewed", "✗ Not Reviewed"),
            ("ai_approved", "AI: Approved"),
            ("ai_rejected", "AI: Rejected"),
            ("ai_needs_review", "AI: Needs Review"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "reviewed":
            return queryset.filter(ai_review_result__isnull=False)
        if self.value() == "not_reviewed":
            return queryset.filter(ai_review_result__isnull=True)
        if self.value() == "ai_approved":
            return queryset.filter(ai_review_result__decision="approved")
        if self.value() == "ai_rejected":
            return queryset.filter(ai_review_result__decision="rejected")
        if self.value() == "ai_needs_review":
            return queryset.filter(ai_review_result__decision="needs_review")
        return queryset


class PipelineStageFilter(admin.SimpleListFilter):
    """
    Single unified filter for the submission pipeline.
    
    Action-oriented: tells you what to DO, not just status.
    Replaces the confusing combination of status/enrichment/review filters.
    """
    title = "📊 pipeline"
    parameter_name = "pipeline"

    def lookups(self, request, model_admin):
        return [
            # === YOUR ACTION ITEMS ===
            ("approve", "🟢 Approve These (AI approved, no flags)"),
            ("reject", "🔴 Reject These (AI rejected)"),
            ("review", "🟡 Review These (needs your decision)"),
            
            # === PIPELINE STAGES ===
            ("waiting_enrich", "⏳ Needs Enrichment"),
            ("waiting_ai", "⏳ Needs AI Review"),
            
            # === DONE ===
            ("done_approved", "✅ Approved"),
            ("done_rejected", "❌ Rejected"),
            
            # === DEBUG ===
            ("all_pending", "📋 All Pending"),
        ]

    def queryset(self, request, queryset):
        val = self.value()
        
        if val == "approve":
            # AI approved + no manual review flag + still pending
            return queryset.filter(
                status=SubmissionStatus.PENDING,
                ai_review_result__decision="approved",
                needs_manual_review=False,
            )
        
        if val == "reject":
            # AI rejected + still pending
            return queryset.filter(
                status=SubmissionStatus.PENDING,
                ai_review_result__decision="rejected",
            )
        
        if val == "review":
            # Needs human decision: AI unsure OR system flagged
            return queryset.filter(
                status=SubmissionStatus.PENDING,
            ).filter(
                models.Q(ai_review_result__decision="needs_review") |
                models.Q(needs_manual_review=True)
            )
        
        if val == "waiting_enrich":
            return queryset.filter(
                status=SubmissionStatus.PENDING,
                enrichment_data__isnull=True,
            )
        
        if val == "waiting_ai":
            return queryset.filter(
                status=SubmissionStatus.PENDING,
                enrichment_data__isnull=False,
                ai_review_result__isnull=True,
            )
        
        if val == "done_approved":
            return queryset.filter(status=SubmissionStatus.APPROVED)
        
        if val == "done_rejected":
            return queryset.filter(status=SubmissionStatus.REJECTED)
        
        if val == "all_pending":
            return queryset.filter(status=SubmissionStatus.PENDING)
        
        return queryset


@admin.register(AgentSubmission)
class AgentSubmissionAdmin(admin.ModelAdmin):
    list_display = [
        "agent_name", 
        "website_link", 
        "pipeline_badge",  # Single badge showing pipeline stage
        "ai_decision_badge",  # What AI decided
        "source", 
        "submitted_at",
    ]
    list_filter = [
        # Primary filter - use this for your workflow
        PipelineStageFilter,
        # Secondary filters for edge cases
        "source",
        "submitted_at",
    ]
    search_fields = ["email", "agent_name", "agent_website", "agent_description"]
    readonly_fields = [
        "submitted_at", "reviewed_at",
        # Pretty displays
        "website_preview",
        "quick_summary",
        "logo_preview",
        "enrichment_pretty",
        "ai_review_pretty",
        "screenshot_preview",
    ]
    actions = ["enrich_selected_submissions", "review_selected_submissions", "approve_and_create_agent", "reject_submission"]

    fieldsets = (
        ("Submission Details", {
            "fields": ("source", "email", "agent_name", "agent_website", "website_preview", "agent_description", "submitted_at")
        }),
        ("📊 Quick Summary", {
            "fields": ("quick_summary",),
            "description": "Key data at a glance from enrichment and AI review."
        }),
        ("🖼️ Media", {
            "fields": ("logo_preview", "screenshot_preview"),
            "description": "Downloaded during enrichment (Firecrawl URLs expire in 24h)."
        }),
        ("🔍 Enrichment Data (Firecrawl)", {
            "fields": ("enrichment_pretty",),
            "description": "Full scraped data from the website."
        }),
        ("🤖 AI Review Result", {
            "fields": ("ai_review_pretty", "needs_manual_review"),
            "description": "AI review does NOT auto-approve. Human makes final decision."
        }),
        ("✍️ Manual Review (Human)", {
            "fields": ("status", "reviewer", "reviewer_notes", "reviewed_at", "agent"),
            "description": "Make final decision here."
        }),
    )
    
    @admin.display(description="Website")
    def website_link(self, obj: AgentSubmission) -> str:
        """Clickable website link in list view."""
        if obj.agent_website:
            # Convert to string to avoid SafeString issues with format_html
            url = str(obj.agent_website)
            display_text = url[:40] + "..." if len(url) > 40 else url
            return format_html(
                '<a href="{}" target="_blank" title="{}" style="max-width:200px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{}</a>',
                url,
                url,
                display_text,
            )
        return "-"
    
    @admin.display(description="Website Preview")
    def website_preview(self, obj: AgentSubmission) -> str:
        """Website link with open button."""
        if not obj.agent_website:
            return "-"
        # Convert to string to avoid SafeString issues with format_html
        url = str(obj.agent_website)
        return format_html(
            '<a href="{}" target="_blank" class="button" '
            'style="background:#0ea5e9;color:white;padding:5px 15px;text-decoration:none;border-radius:4px;">'
            '🔗 Open Website</a> <code style="margin-left:10px;">{}</code>',
            url,
            url,
        )
    
    @admin.display(description="Quick Summary")
    def quick_summary(self, obj: AgentSubmission) -> str:
        """Show key data from enrichment and review at a glance."""
        parts = []
        
        # Enrichment summary
        if obj.enrichment_data:
            content = obj.enrichment_data.get("content_data") or {}
            
            # URL extraction info
            url_info = obj.enrichment_data.get("_url_extraction")
            if url_info and url_info.get("extraction_performed"):
                parts.append(format_html(
                    '<div style="background:#fef3c7;padding:8px;border-radius:4px;margin-bottom:8px;">'
                    '🔀 <strong>URL Extracted:</strong> Original was <code>{}</code></div>',
                    url_info.get("original_url", "?")[:60],
                ))
            
            # Key fields table - use escape() on all user-controlled values
            fields_html = '<table style="width:100%;border-collapse:collapse;">'
            
            short_desc = content.get("short_description") or "—"
            if len(short_desc) > 150:
                short_desc = short_desc[:150] + "..."
            
            key_fields = [
                ("Short Description", escape(short_desc)),
                ("Category", escape(content.get("category") or "—")),
                ("Pricing", escape(content.get("pricing_model") or "—")),
                ("Industry", escape(content.get("industry") or "—")),
                ("Open Source", "✅ Yes" if content.get("is_open_source") else "—"),
            ]
            
            for label, value in key_fields:
                # label is hardcoded, value is already escaped above
                fields_html += f'<tr><td style="padding:4px;font-weight:bold;width:120px;">{label}</td><td style="padding:4px;">{value}</td></tr>'
            
            fields_html += '</table>'
            parts.append(fields_html)
            
            # Features (if any) - escape each feature
            features = content.get("features") or []
            if features:
                # Escape each feature name
                features_escaped = [escape(f) for f in features[:5]]
                features_list = ", ".join(features_escaped)
                if len(features) > 5:
                    features_list += f" (+{len(features) - 5} more)"
                parts.append(f'<div style="margin-top:8px;"><strong>Features:</strong> {features_list}</div>')
        else:
            parts.append('<div style="color:#9ca3af;font-style:italic;">Not enriched yet</div>')
        
        # AI Review summary
        if obj.ai_review_result:
            result = obj.ai_review_result
            decision = result.get("decision", "unknown")
            confidence = result.get("confidence", 0)
            reasoning = result.get("reasoning", "")[:200]
            flags = result.get("flags", [])
            
            if decision == "approved":
                color, bg = "#059669", "#d1fae5"
            elif decision == "rejected":
                color, bg = "#dc2626", "#fee2e2"
            else:
                color, bg = "#d97706", "#fef3c7"
            
            # Format confidence as percentage string to avoid format_html issues
            confidence_pct = f"{float(confidence):.0%}"
            parts.append(format_html(
                '<div style="background:{};padding:10px;border-radius:4px;margin-top:10px;border-left:4px solid {};">'
                '<strong>🤖 AI:</strong> <span style="color:{};">{} ({})</span><br>'
                '<small style="color:#6b7280;">{}</small>'
                '{}</div>',
                bg, color, color, decision.upper(), confidence_pct,
                reasoning + "..." if len(result.get("reasoning", "")) > 200 else reasoning,
                format_html('<br><strong>Flags:</strong> {}', ", ".join(flags)) if flags else "",
            ))
        
        return mark_safe("".join(parts)) if parts else "-"
    
    @admin.display(description="Logo")
    def logo_preview(self, obj: AgentSubmission) -> str:
        """
        Show logo - prefers downloaded file over URL (URLs expire in 24h).
        """
        # Prefer downloaded logo (doesn't expire)
        if obj.logo:
            return format_html(
                '<div style="margin-bottom:5px;">'
                '<span style="color:#059669;">✓ Downloaded</span>'
                '</div>'
                '<img src="{}" style="max-width:100px;max-height:100px;border-radius:8px;border:1px solid #e5e7eb;" />',
                obj.logo.url,
            )
        
        # Fallback to URL from enrichment_data (may be expired)
        if not obj.enrichment_data:
            return "-"
        
        logo_url = obj.enrichment_data.get("logo_url")
        if not logo_url:
            return '<span style="color:#9ca3af;">No logo</span>'
        
        # Show warning that URL may be expired
        return format_html(
            '<div style="margin-bottom:5px;">'
            '<span style="color:#d97706;">⚠️ URL only (may be expired)</span>'
            '</div>'
            '<img src="{}" style="max-width:100px;max-height:100px;border-radius:8px;border:1px solid #e5e7eb;" '
            'onerror="this.style.display=\'none\';this.parentElement.innerHTML+=\'<span style=color:#dc2626>Image expired</span>\'" />',
            logo_url,
        )
    
    @admin.display(description="Screenshot")
    def screenshot_preview(self, obj: AgentSubmission) -> str:
        """
        Show screenshot - prefers downloaded file over URL (URLs expire in 24h).
        """
        # Prefer downloaded screenshot (doesn't expire)
        if obj.screenshot:
            return format_html(
                '<div style="margin-bottom:5px;">'
                '<span style="color:#059669;">✓ Downloaded</span>'
                '</div>'
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-width:400px;max-height:250px;border-radius:8px;border:1px solid #e5e7eb;" />'
                '</a>',
                obj.screenshot.url,
                obj.screenshot.url,
            )
        
        # Fallback to URL from enrichment_data (may be expired)
        if not obj.enrichment_data:
            return "-"
        
        screenshot_url = obj.enrichment_data.get("screenshot_url")
        if not screenshot_url:
            return '<span style="color:#9ca3af;">No screenshot</span>'
        
        # Show warning that URL may be expired
        return format_html(
            '<div style="margin-bottom:5px;">'
            '<span style="color:#d97706;">⚠️ URL only (may be expired)</span>'
            '</div>'
            '<a href="{}" target="_blank" rel="noopener noreferrer">'
            '<img src="{}" style="max-width:400px;max-height:250px;border-radius:8px;border:1px solid #e5e7eb;" '
            'onerror="this.style.display=\'none\';this.parentElement.innerHTML=\'<span style=color:#dc2626>Image expired or unavailable</span>\'" />'
            '</a>',
            screenshot_url,
            screenshot_url,
        )
    
    @admin.display(description="Enrichment Data (JSON)")
    def enrichment_pretty(self, obj: AgentSubmission) -> str:
        """Pretty-printed enrichment JSON."""
        return mark_safe(pretty_json_html(obj.enrichment_data, max_height="500px"))
    
    @admin.display(description="AI Review (JSON)")
    def ai_review_pretty(self, obj: AgentSubmission) -> str:
        """Pretty-printed AI review JSON."""
        return mark_safe(pretty_json_html(obj.ai_review_result, max_height="300px"))
    
    @admin.display(description="Manual Review", boolean=True)
    def needs_manual_review_badge(self, obj: AgentSubmission) -> bool:
        """Show manual review flag as boolean icon."""
        return obj.needs_manual_review
    
    @admin.display(description="Stage")
    def pipeline_badge(self, obj: AgentSubmission) -> str:
        """Show current pipeline stage as a clear badge."""
        if obj.status == SubmissionStatus.APPROVED:
            return format_html('<span style="background:#059669;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">✅ Approved</span>')
        if obj.status == SubmissionStatus.REJECTED:
            return format_html('<span style="background:#dc2626;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">❌ Rejected</span>')
        
        # Pending - show where in pipeline
        if not obj.enrichment_data:
            return format_html('<span style="background:#6b7280;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">⏳ Needs Enrichment</span>')
        
        if not obj.ai_review_result:
            return format_html('<span style="background:#6b7280;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">⏳ Needs AI Review</span>')
        
        # Has AI review - show action needed
        decision = obj.ai_review_result.get("decision", "")
        if obj.needs_manual_review or decision == "needs_review":
            return format_html('<span style="background:#d97706;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">🟡 Review</span>')
        if decision == "approved":
            return format_html('<span style="background:#059669;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">🟢 Approve</span>')
        if decision == "rejected":
            return format_html('<span style="background:#dc2626;color:white;padding:2px 8px;border-radius:4px;font-size:11px;">🔴 Reject</span>')
        
        return format_html('<span style="color:#6b7280;">—</span>')
    
    @admin.display(description="AI Decision")
    def ai_decision_badge(self, obj: AgentSubmission) -> str:
        """Show what the AI decided (simple)."""
        if not obj.ai_review_result:
            return format_html('<span style="color:#9ca3af;">—</span>')
        
        decision = obj.ai_review_result.get("decision", "")
        confidence = obj.ai_review_result.get("confidence", 0)
        
        if decision == "approved":
            color = "#059669" if confidence >= 0.8 else "#10b981"
            confidence_pct = f"{float(confidence):.0%}"
            return format_html('<span style="color:{};">✓ {}</span>', color, confidence_pct)
        if decision == "rejected":
            reason = obj.ai_review_result.get("rejection_reason", "")
            short_reason = reason[:20] + "..." if len(reason) > 20 else reason
            return format_html('<span style="color:#dc2626;" title="{}">✗ {}</span>', reason, short_reason or "rejected")
        if decision == "needs_review":
            return format_html('<span style="color:#d97706;">? unsure</span>')
        
        return format_html('<span style="color:#6b7280;">{}</span>', decision)
    
    @admin.display(description="AI Review")
    def ai_review_status(self, obj: AgentSubmission) -> str:
        """Show AI review decision and confidence."""
        if not obj.ai_review_result:
            return format_html('<span style="color: #6b7280;">—</span>')
        
        result = obj.ai_review_result
        decision = result.get("decision", "unknown")
        confidence = result.get("confidence", 0)
        
        if decision == "approved":
            color = "#059669"
            icon = "✓"
        elif decision == "rejected":
            color = "#dc2626"
            icon = "✗"
        else:
            color = "#d97706"
            icon = "?"
        
        confidence_pct = f"{confidence:.0%}"
        return format_html(
            '<span style="color: {};">{} {} ({})</span>',
            color, icon, decision, confidence_pct
        )

    @admin.display(description="Enrichment")
    def enrichment_status(self, obj: AgentSubmission) -> str:
        """Show enrichment status."""
        if not obj.enrichment_data:
            return format_html('<span style="color: #6b7280;">Not enriched</span>')
        
        if obj.enrichment_data.get("success"):
            return format_html('<span style="color: #059669;">✓ Enriched</span>')
        
        return format_html('<span style="color: #dc2626;">✗ Failed</span>')

    @admin.display(description="Created Agent")
    def agent_link(self, obj: AgentSubmission) -> str:
        """Show link to created agent if it exists."""
        if obj.agent:
            url = reverse("admin:agents_agent_change", args=[obj.agent.pk])
            return format_html('<a href="{}">{}</a>', url, obj.agent.name)
        return "-"

    @admin.action(description="🔄 Enrich selected submissions")
    def enrich_selected_submissions(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Enrich selected submissions with data from their websites."""
        count = 0
        for submission in queryset:
            enrich_submission_task.delay(submission.id)
            count += 1
        
        if count > 0:
            messages.success(
                request,
                f"Queued enrichment for {count} submission(s). Refresh to see results."
            )

    @admin.action(description="🤖 AI Review (no auto-approve)")
    def review_selected_submissions(self, request: HttpRequest, queryset: QuerySet) -> None:
        """
        Run AI review on selected submissions.
        
        Sets ai_review_result and needs_manual_review flag.
        Does NOT auto-approve/reject - human must make final decision.
        """
        service = ReviewService()
        reviewed_count = 0
        
        for submission in queryset:
            try:
                service.review_submission(submission, auto_apply=False)
                reviewed_count += 1
            except Exception as e:
                messages.error(
                    request,
                    f"Failed to review '{submission.agent_name}': {str(e)}"
                )
        
        if reviewed_count > 0:
            messages.success(
                request,
                f"AI review complete for {reviewed_count} submission(s). "
                "Check 'AI Review' column for results. Manual approval still required."
            )

    @admin.action(description="✅ Approve and create agent (with enrichment)")
    def approve_and_create_agent(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Approve selected submissions and create agent records using enrichment data."""
        service = EnrichmentService()
        approved_count = 0

        for submission in queryset.filter(status=SubmissionStatus.PENDING):
            try:
                with transaction.atomic():
                    # Ensure submission is enriched
                    if not submission.enrichment_data:
                        service.enrich_submission(submission)
                        submission.refresh_from_db()

                    # Verify enrichment succeeded before creating agent
                    if not submission.enrichment_data.get("success"):
                        error_msg = submission.enrichment_data.get("error_message", "Unknown error")
                        messages.warning(
                            request,
                            f"Skipped '{submission.agent_name}': Enrichment failed - {error_msg}"
                        )
                        continue

                    # Create agent from enriched submission (duplicate check is built-in)
                    agent = service.create_agent_from_submission(submission, user=request.user)
                    agent.status = AgentStatus.PUBLISHED
                    agent.save()

                    # Update submission
                    submission.status = SubmissionStatus.APPROVED
                    submission.agent = agent
                    submission.reviewer = request.user
                    submission.reviewed_at = timezone.now()
                    submission.save()

                    approved_count += 1

            except DuplicateAgentError as e:
                messages.warning(
                    request,
                    f"Skipped '{submission.agent_name}': {e}"
                )

            except Exception as e:
                messages.error(
                    request,
                    f"Failed to approve '{submission.agent_name}': {str(e)}"
                )

        if approved_count > 0:
            messages.success(
                request,
                f"Successfully approved {approved_count} submission(s) and created enriched agent(s)"
            )

    @admin.action(description="❌ Reject selected submissions")
    def reject_submission(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Reject selected submissions."""
        updated = queryset.filter(status=SubmissionStatus.PENDING).update(
            status=SubmissionStatus.REJECTED,
            reviewed_at=timezone.now(),
            reviewer=request.user,
        )

        if updated > 0:
            messages.success(request, f"Rejected {updated} submission(s)")
        else:
            messages.warning(request, "No pending submissions were rejected")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:submission_id>/enrich/",
                self.admin_site.admin_view(self.enrich_single_submission),
                name="agentsubmission-enrich",
            ),
            path(
                "<int:submission_id>/approve/",
                self.admin_site.admin_view(self.approve_single_submission),
                name="agentsubmission-approve",
            ),
            path(
                "<int:submission_id>/reject/",
                self.admin_site.admin_view(self.reject_single_submission),
                name="agentsubmission-reject",
            ),
            path(
                "<int:submission_id>/review/",
                self.admin_site.admin_view(self.review_single_submission),
                name="agentsubmission-review",
            ),
        ]
        return custom_urls + urls

    def enrich_single_submission(self, request: HttpRequest, submission_id: int):
        """Enrich a single submission immediately."""
        submission = self.get_object(request, submission_id)

        try:
            service = EnrichmentService()
            service.enrich_submission(submission)
            
            if submission.enrichment_data.get("success"):
                messages.success(request, f"✅ Enriched '{submission.agent_name}'")
            else:
                error = submission.enrichment_data.get("error_message", "Unknown error")
                messages.error(request, f"❌ Enrichment failed: {error}")
        except Exception as e:
            messages.error(request, f"Enrichment error: {str(e)}")

        return redirect("admin:agents_agentsubmission_change", submission_id)

    def approve_single_submission(self, request: HttpRequest, submission_id: int):
        """Approve a single submission and create agent with enrichment data."""
        submission = self.get_object(request, submission_id)

        if submission.status != SubmissionStatus.PENDING:
            messages.warning(
                request,
                f"Submission is already {submission.get_status_display()}."
            )
            return redirect("admin:agents_agentsubmission_change", submission_id)

        try:
            with transaction.atomic():
                service = EnrichmentService()

                # Ensure enriched
                if not submission.enrichment_data:
                    service.enrich_submission(submission)
                    submission.refresh_from_db()

                # Verify enrichment succeeded before creating agent
                if not submission.enrichment_data.get("success"):
                    error_msg = submission.enrichment_data.get("error_message", "Unknown error")
                    messages.error(
                        request,
                        f"Cannot approve: Enrichment failed - {error_msg}. "
                        "Please re-run enrichment."
                    )
                    return redirect("admin:agents_agentsubmission_change", submission_id)

                # Create agent (duplicate check is built-in)
                agent = service.create_agent_from_submission(submission, user=request.user)
                agent.status = AgentStatus.PUBLISHED
                agent.save()

                # Update submission
                submission.status = SubmissionStatus.APPROVED
                submission.agent = agent
                submission.reviewer = request.user
                submission.reviewed_at = timezone.now()
                submission.save()

                agent_url = reverse("admin:agents_agent_change", args=[agent.pk])
                messages.success(
                    request,
                    format_html(
                        '✅ Approved! Created enriched agent "{}". '
                        '<a href="{}">Edit agent</a> to review and publish.',
                        agent.name,
                        agent_url,
                    ),
                )

        except DuplicateAgentError as e:
            messages.error(request, f"Cannot approve: {e}")

        except Exception as e:
            messages.error(request, f"Failed to approve submission: {str(e)}")

        return redirect("admin:agents_agentsubmission_change", submission_id)

    def reject_single_submission(self, request: HttpRequest, submission_id: int):
        """Reject a single submission."""
        submission = self.get_object(request, submission_id)

        if submission.status != SubmissionStatus.PENDING:
            messages.warning(
                request,
                f"Submission is already {submission.get_status_display()}."
            )
            return redirect("admin:agents_agentsubmission_change", submission_id)

        submission.status = SubmissionStatus.REJECTED
        submission.reviewer = request.user
        submission.reviewed_at = timezone.now()
        submission.save()

        messages.success(request, '❌ Submission rejected.')
        return redirect("admin:agents_agentsubmission_change", submission_id)

    def review_single_submission(self, request: HttpRequest, submission_id: int):
        """Run AI review on a single submission (no auto-approve)."""
        submission = self.get_object(request, submission_id)

        try:
            service = ReviewService()
            service.review_submission(submission, auto_apply=False)
            
            result = submission.ai_review_result
            if result:
                decision = result.get("decision", "unknown")
                confidence = result.get("confidence", 0)
                messages.success(
                    request,
                    f"🤖 AI Review: {decision} ({confidence:.0%} confidence). "
                    "Manual approval still required."
                )
            else:
                messages.warning(request, "Review completed but no result stored.")
        except Exception as e:
            messages.error(request, f"AI Review error: {str(e)}")

        return redirect("admin:agents_agentsubmission_change", submission_id)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_review_buttons"] = True
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj and not add:
            # Always show enrich button
            context["enrich_button"] = format_html(
                '<a class="button" href="{}" style="background-color: #0ea5e9; color: white; margin-right: 10px;">🔄 Enrich</a>',
                reverse("admin:agentsubmission-enrich", args=[obj.pk]),
            )
            
            # Always show AI review button
            context["review_button"] = format_html(
                '<a class="button" href="{}" style="background-color: #8b5cf6; color: white; margin-right: 10px;">🤖 AI Review</a>',
                reverse("admin:agentsubmission-review", args=[obj.pk]),
            )
            
            # Show approve/reject only for pending
            if obj.status == SubmissionStatus.PENDING:
                context["approve_button"] = format_html(
                    '<a class="button" href="{}" style="background-color: #059669; color: white; margin-right: 10px;">✅ Approve & Create Agent</a>',
                    reverse("admin:agentsubmission-approve", args=[obj.pk]),
                )
                context["reject_button"] = format_html(
                    '<a class="button" href="{}" style="background-color: #dc2626; color: white;" '
                    'onclick="return confirm(\'Are you sure you want to reject this submission?\');">❌ Reject</a>',
                    reverse("admin:agentsubmission-reject", args=[obj.pk]),
                )
        return super().render_change_form(request, context, add, change, form_url, obj)
