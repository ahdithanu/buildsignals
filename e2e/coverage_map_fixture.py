"""Synthetic multi-state inventory through the existing local ingestion path."""
import csv
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.ingestion import IngestionSourceCreate
from app.services.ingestion.service import create_source, execute_source_run
from app.utils.org_scope import RequestContext, reset_current_context, set_current_context


def seed_coverage_map_fixture(db, organization_id, user_id, directory):
    token = set_current_context(RequestContext(organization_id, user_id))
    try:
        now = datetime.now(timezone.utc).isoformat()
        groups = (
            ('permit', 'FL', 'Orlando', 125, 74, 28.46, -81.27),
            ('permit', 'TX', 'Austin', 17, 17, 30.26, -97.74),
            ('permit', '', '', 3, 0, None, None),
            ('planning', 'OH', 'Columbus', 2, 0, None, None),
            ('parcel', 'FL', 'Orlando', 70, 70, 28.46, -81.27),
        )
        for index, (kind, state, city, count, mapped, latitude, longitude) in enumerate(groups):
            path = Path(directory) / f'synthetic-coverage-{index}.csv'
            fields = ['id', 'address', 'city', 'state', 'title', 'latitude', 'longitude', 'filed', 'stage']
            with path.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                for number in range(count):
                    writer.writerow({
                        'id': f'synthetic-coverage-{index}-{number:03}',
                        'address': f'{number + 1} Synthetic Coverage Street', 'city': city, 'state': state,
                        'title': f'Synthetic {kind} {state or "unknown"} {number:03}',
                        'latitude': latitude + number * .00001 if number < mapped else '',
                        'longitude': longitude if number < mapped else '', 'filed': now, 'stage': 'pre_approval',
                    })
            mappings = {'id': 'source_record_id', 'address': 'address', 'city': 'city', 'state': 'state',
                        'latitude': 'latitude', 'longitude': 'longitude'}
            if kind == 'permit':
                mappings.update(title='project_name', filed='filed_at', stage='approval_stage')
            elif kind == 'planning':
                mappings.update(title='title', filed='published_at', stage='stage')
            source = create_source(db, IngestionSourceCreate(
                key=f'synthetic-coverage-{index}', name='SYNTHETIC coverage fixture', adapter='csv',
                record_type=kind, base_url=str(path), jurisdiction=f'{city}, {state}' if state else None,
                field_mappings=[{'source_field': key, 'canonical_field': value} for key, value in mappings.items()],
            ))
            db.commit()
            result = execute_source_run(db, source, max_pages=2)
            assert result.status == 'completed' and result.records_failed == 0, (
                kind, index, result.status, result.records_failed, result.error_message,
            )
            assert result.records_inserted == count
    finally:
        reset_current_context(token)
