from datetime import datetime
import csv
from pathlib import Path
import requests
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings

from aiagents_directory.agents.models import Agent, Screenshot


def download_image(url: str) -> tuple[str, File]:
    """Download image from URL and return as a Django File object."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    # Get filename from URL or use timestamp if none found
    filename = Path(urlparse(url).path).name
    if not filename:
        filename = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}{Path(url).suffix}"
    
    # Save to temp file first
    img_temp = NamedTemporaryFile(delete=True)
    img_temp.write(response.content)
    img_temp.flush()
    
    return filename, File(img_temp)


class Command(BaseCommand):
    help = "Update agents data from a CSV file, skipping featured agents and those with custom logos"

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv_file'])
        dry_run = options['dry_run']
        
        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f'File not found: {csv_path}'))
            return
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    agent = Agent.objects.get(name=row['name'])
                    
                    # Skip featured agents
                    if agent.featured:
                        self.stdout.write(f"Skipping featured agent: {agent.name}")
                        continue
                    
                    # Skip agents with custom logos
                    if not agent.logo.name.endswith('default-logo.png'):
                        self.stdout.write(f"Skipping agent with custom logo: {agent.name}")
                        continue
                    
                    updates = []
                    
                    # Update description if provided
                    if row.get('fullDescription'):
                        if not dry_run:
                            agent.description = row['fullDescription']
                        updates.append('description')
                    
                    # Update logo if provided
                    if row.get('logoUrl'):
                        try:
                            if not dry_run:
                                filename, file_obj = download_image(row['logoUrl'])
                                agent.logo.save(filename, file_obj, save=False)
                            updates.append('logo')
                        except Exception as e:
                            self.stderr.write(
                                self.style.WARNING(f"Failed to download logo for {agent.name}: {e}")
                            )
                    
                    # Add screenshot if provided
                    if row.get('screenshotUrl'):
                        try:
                            if not dry_run:
                                filename, file_obj = download_image(row['screenshotUrl'])
                                Screenshot.objects.create(
                                    agent=agent,
                                    image=File(file_obj),
                                    is_primary=not agent.screenshots.exists()
                                )
                            updates.append('screenshot')
                        except Exception as e:
                            self.stderr.write(
                                self.style.WARNING(f"Failed to download screenshot for {agent.name}: {e}")
                            )
                    
                    if updates:
                        if not dry_run:
                            agent.save()
                        status = "Would update" if dry_run else "Updated"
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"{status} {agent.name} with: {', '.join(updates)}"
                            )
                        )
                    
                except Agent.DoesNotExist:
                    self.stderr.write(
                        self.style.WARNING(f"Agent not found: {row['name']}")
                    )
                except Exception as e:
                    self.stderr.write(
                        self.style.ERROR(f"Error processing {row.get('name', 'unknown')}: {e}")
                    ) 