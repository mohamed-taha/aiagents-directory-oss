"""
Management command to import agent submissions from Tally CSV export.

Usage:
    python manage.py import_tally_submissions <csv_file_path> [--dry-run] [--auto-approve]

Expected CSV columns from Tally export:
    - Your Email (required)
    - Example: Cursor (required - agent name)
    - What is the website of the agent? (required)
    - Please provide a brief description of the agent (required)
    - Submitted at (optional - will preserve original submission date)
    - Submission ID (ignored)
    - Respondent ID (ignored)
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from aiagents_directory.agents.models import AgentSubmission, SubmissionStatus


class Command(BaseCommand):
    help = "Import agent submissions from Tally CSV export"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            'csv_file',
            type=str,
            help='Path to the Tally CSV export file'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be imported without saving to database',
        )
        parser.add_argument(
            '--auto-approve',
            action='store_true',
            help='Automatically mark imported submissions as APPROVED',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        csv_path = Path(options['csv_file'])
        dry_run = options['dry_run']
        auto_approve = options['auto_approve']
        
        if not csv_path.exists():
            raise CommandError(f'File not found: {csv_path}')
        
        self.stdout.write(self.style.SUCCESS(f'\n📂 Reading CSV from: {csv_path}'))
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No data will be saved\n'))
        
        imported_count = 0
        skipped_count = 0
        error_count = 0
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Display available columns
            self.stdout.write(self.style.WARNING(f'Available columns: {", ".join(reader.fieldnames or [])}\n'))
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                try:
                    # Extract data with flexible column name matching
                    email = self._extract_field(row, [
                        'Your Email',  # Tally's actual column name
                        'email', 
                        'Email', 
                        'Respondent email', 
                        'respondent_email'
                    ])
                    agent_name = self._extract_field(row, [
                        'Example: Cursor',  # Tally's actual column name
                        'agent_name', 
                        'Agent Name',
                        'What is the name of the agent?',
                        'name'
                    ])
                    agent_website = self._extract_field(row, [
                        'What is the website of the agent?',  # Tally's actual column name
                        'agent_website',
                        'Website',
                        'website',
                        'url'
                    ])
                    agent_description = self._extract_field(row, [
                        'Please provide a brief description of the agent',  # Tally's actual column name
                        'agent_description',
                        'Description',
                        'description',
                        'brief_description'
                    ])
                    
                    # Optional: submitted_at date
                    submitted_at_str = self._extract_field(row, [
                        'Submitted at',  # Tally's actual column name
                        'submitted_at',
                        'Response created at',
                        'created_at'
                    ], required=False)
                    
                    # Validate required fields
                    if not all([email, agent_name, agent_website, agent_description]):
                        missing = []
                        if not email: missing.append('email')
                        if not agent_name: missing.append('agent_name')
                        if not agent_website: missing.append('agent_website')
                        if not agent_description: missing.append('agent_description')
                        
                        self.stdout.write(
                            self.style.ERROR(
                                f'❌ Row {row_num}: Missing required fields: {", ".join(missing)}'
                            )
                        )
                        error_count += 1
                        continue
                    
                    # Check if already imported (by email + agent_name)
                    existing = AgentSubmission.objects.filter(
                        email=email,
                        agent_name=agent_name
                    ).first()
                    
                    if existing:
                        self.stdout.write(
                            self.style.WARNING(
                                f'⏭️  Row {row_num}: Already exists - {agent_name} ({email})'
                            )
                        )
                        skipped_count += 1
                        continue
                    
                    # Parse submitted_at date if available
                    submitted_at = None
                    if submitted_at_str:
                        submitted_at = self._parse_date(submitted_at_str)
                    
                    if dry_run:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✓ Row {row_num}: Would import - {agent_name} ({email})'
                            )
                        )
                        imported_count += 1
                    else:
                        # Create submission
                        submission = AgentSubmission.objects.create(
                            email=email,
                            agent_name=agent_name,
                            agent_website=agent_website,
                            agent_description=agent_description,
                            status=SubmissionStatus.APPROVED if auto_approve else SubmissionStatus.PENDING,
                        )
                        
                        # Update submitted_at if we have it
                        if submitted_at:
                            submission.submitted_at = submitted_at
                            submission.save(update_fields=['submitted_at'])
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'✅ Row {row_num}: Imported - {agent_name} ({email})'
                            )
                        )
                        imported_count += 1
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'❌ Row {row_num}: Error - {str(e)}'
                        )
                    )
                    error_count += 1
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'\n📊 IMPORT SUMMARY:'))
        self.stdout.write(f'  ✅ Imported: {imported_count}')
        self.stdout.write(f'  ⏭️  Skipped (duplicates): {skipped_count}')
        self.stdout.write(f'  ❌ Errors: {error_count}')
        self.stdout.write('='*60 + '\n')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '💡 Run without --dry-run to actually import the data'
                )
            )

    def _extract_field(self, row: dict[str, str], possible_names: list[str], required: bool = True) -> str:
        """Try to extract field value from various possible column names."""
        for name in possible_names:
            if name in row and row[name].strip():
                # Clean up multiline text and extra whitespace
                value = row[name].strip()
                # Replace multiple newlines with single newline
                value = '\n'.join(line.strip() for line in value.splitlines() if line.strip())
                return value
        
        if required:
            return ''
        return ''

    def _parse_date(self, date_str: str) -> Any:
        """Parse date string to datetime object."""
        # Try common date formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M',
            '%m/%d/%Y',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return timezone.make_aware(dt, timezone.get_current_timezone())
            except ValueError:
                continue
        
        # If all formats fail, return None
        return None

