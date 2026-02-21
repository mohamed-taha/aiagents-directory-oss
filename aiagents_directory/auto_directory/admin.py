"""
Admin configuration for the auto_directory app.

Provides admin interface for:
- EnrichmentLog: Audit trail for agent enrichment operations
- SourcingRun: Audit trail for agent sourcing/discovery operations
"""

from django.contrib import admin, messages
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from aiagents_directory.auto_directory.models import EnrichmentLog, SourcingRun


@admin.register(EnrichmentLog)
class EnrichmentLogAdmin(admin.ModelAdmin):
    """Admin for viewing enrichment audit logs."""
    
    list_display = [
        "agent",
        "status_badge",
        "applied_fields_display",
        "created_at",
        "created_by",
    ]
    list_filter = ["success", "created_at", "created_by"]
    search_fields = ["agent__name", "error_message"]
    readonly_fields = [
        "agent",
        "previous_data",
        "extracted_data",
        "applied_fields",
        "success",
        "error_message",
        "created_at",
        "created_by",
    ]
    ordering = ["-created_at"]
    
    fieldsets = (
        (None, {
            "fields": ("agent", "success", "error_message", "created_at", "created_by")
        }),
        (_("Applied Changes"), {
            "fields": ("applied_fields",),
        }),
        (_("Data Snapshot"), {
            "fields": ("previous_data", "extracted_data"),
            "classes": ("collapse",),
        }),
    )
    
    def has_add_permission(self, request: HttpRequest) -> bool:
        """Logs are created by the system, not manually."""
        return False
    
    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Logs are read-only."""
        return False
    
    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Allow deletion for cleanup purposes."""
        return True
    
    @admin.display(description=_("Status"))
    def status_badge(self, obj: EnrichmentLog) -> str:
        """Display success/failure as colored badge."""
        if obj.success:
            return format_html(
                '<span style="color: #059669; font-weight: bold;">✓ Success</span>'
            )
        return format_html(
            '<span style="color: #dc2626; font-weight: bold;">✗ Failed</span>'
        )
    
    @admin.display(description=_("Applied Fields"))
    def applied_fields_display(self, obj: EnrichmentLog) -> str:
        """Display applied fields as comma-separated list."""
        if not obj.applied_fields:
            return "-"
        return ", ".join(obj.applied_fields)


@admin.register(SourcingRun)
class SourcingRunAdmin(admin.ModelAdmin):
    """Admin for viewing and managing sourcing runs."""
    
    list_display = [
        "source_id",
        "status_badge",
        "discovered_count",
        "new_count",
        "skipped_count",
        "duration_display",
        "started_at",
        "created_by",
    ]
    list_filter = ["source_id", "success", "started_at", "created_by"]
    search_fields = ["source_id", "error_message"]
    readonly_fields = [
        "source_id",
        "started_at",
        "completed_at",
        "discovered_count",
        "new_count",
        "skipped_count",
        "success",
        "error_message",
        "config",
        "created_submission_ids",
        "created_by",
    ]
    ordering = ["-started_at"]
    date_hierarchy = "started_at"
    
    fieldsets = (
        (None, {
            "fields": (
                "source_id",
                "success",
                "error_message",
                "started_at",
                "completed_at",
                "created_by",
            )
        }),
        (_("Results"), {
            "fields": ("discovered_count", "new_count", "skipped_count"),
        }),
        (_("Details"), {
            "fields": ("config", "created_submission_ids"),
            "classes": ("collapse",),
        }),
    )
    
    actions = ["run_serp_sourcing", "run_serp_sourcing_with_enrich"]
    
    def has_add_permission(self, request: HttpRequest) -> bool:
        """Runs are created by the system or via actions."""
        return False
    
    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Runs are read-only."""
        return False
    
    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Allow deletion for cleanup purposes."""
        return True
    
    @admin.display(description=_("Status"))
    def status_badge(self, obj: SourcingRun) -> str:
        """Display success/failure as colored badge."""
        if obj.success:
            return format_html(
                '<span style="color: #059669; font-weight: bold;">✓ Success</span>'
            )
        return format_html(
            '<span style="color: #dc2626; font-weight: bold;">✗ Failed</span>'
        )
    
    @admin.display(description=_("Duration"))
    def duration_display(self, obj: SourcingRun) -> str:
        """Display run duration."""
        duration = obj.duration_seconds
        if duration is None:
            return "-"
        if duration < 60:
            return f"{duration:.1f}s"
        return f"{duration / 60:.1f}m"
    
    @admin.action(description=_("🔍 Run SERP sourcing (discover only)"))
    def run_serp_sourcing(self, request: HttpRequest, queryset) -> None:
        """Run SERP sourcing without auto-enrichment."""
        self._run_sourcing(request, auto_enrich=False)
    
    @admin.action(description=_("🔍 Run SERP sourcing (with enrichment)"))
    def run_serp_sourcing_with_enrich(self, request: HttpRequest, queryset) -> None:
        """Run SERP sourcing with auto-enrichment."""
        self._run_sourcing(request, auto_enrich=True)
    
    def _run_sourcing(self, request: HttpRequest, auto_enrich: bool) -> None:
        """Execute sourcing run."""
        from aiagents_directory.auto_directory.services import SourcingService
        from aiagents_directory.auto_directory.sources import SerpSource
        
        try:
            service = SourcingService(sources=[SerpSource()])
            runs = service.run_all(
                limit_per_source=50,
                auto_enrich=auto_enrich,
                user=request.user,
            )
            
            for run in runs:
                if run.success:
                    self.message_user(
                        request,
                        _(
                            f"SERP sourcing complete: discovered {run.discovered_count}, "
                            f"{run.new_count} new submissions created"
                        ),
                        messages.SUCCESS,
                    )
                else:
                    self.message_user(
                        request,
                        _(f"SERP sourcing failed: {run.error_message}"),
                        messages.ERROR,
                    )
                    
        except Exception as e:
            self.message_user(
                request,
                _(f"Sourcing error: {str(e)}"),
                messages.ERROR,
            )
