"""Opt-in proof that research test connections use distinct physical backends."""
import os

import pytest
from sqlalchemy import text

from tests.snapshot_postgres_support import verified_snapshot_connection

URL = os.environ.get('SNAPSHOT_TEST_POSTGRES_URL')
RUN_ID = os.environ.get('SNAPSHOT_TEST_RUN_ID', '')
pytestmark = pytest.mark.skipif(not URL, reason='Dedicated disposable PostgreSQL URL not set')


def test_snapshot_connections_have_distinct_postgres_backends():
    with verified_snapshot_connection(URL, RUN_ID) as first:
        with verified_snapshot_connection(URL, RUN_ID) as second:
            first_pid = first.scalar(text('SELECT pg_catalog.pg_backend_pid()'))
            second_pid = second.scalar(text('SELECT pg_catalog.pg_backend_pid()'))
            assert type(first_pid) is int and type(second_pid) is int
            assert first_pid != second_pid
