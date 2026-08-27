"""conftest.py — shared pytest fixtures for MUSKU tests.

Resets the tenant contextvar before every test so contextvar state never leaks
between tests (the multi-tenant uid is stored in a contextvar).
"""
import pytest
import tenant_ctx


@pytest.fixture(autouse=True)
def _reset_tenant_uid():
    tenant_ctx.set_uid(None)
    yield
    tenant_ctx.set_uid(None)
