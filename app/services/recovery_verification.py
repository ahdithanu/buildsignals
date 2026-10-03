"""Rollback-only PostgreSQL isolation probe for an explicitly isolated restored copy."""
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def verify_restored_postgres(engine) -> dict:
    if engine.dialect.name != "postgresql":
        raise ValueError("PostgreSQL required; SQLite cannot validate RLS")
    import app.models  # noqa: F401
    from app.db import Base
    from app.models.mixins import OrgMixin

    expected = sorted({mapper.local_table.name for mapper in Base.registry.mappers
                       if issubclass(mapper.class_, OrgMixin)})
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL statement_timeout = '15s'"))
            connection.execute(text("SET LOCAL lock_timeout = '3s'"))
            role = connection.execute(text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )).one()
            if role.rolsuper or role.rolbypassrls:
                raise ValueError("Use the restricted application role, not a superuser or BYPASSRLS role")
            rows = connection.execute(text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) AS has_policy "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
            ), {"tables": expected}).all()
            protected = {row.relname for row in rows if row.relrowsecurity and row.relforcerowsecurity and row.has_policy}
            missing = sorted(set(expected) - protected)
            if missing:
                return {"passed": False, "unprotected_or_missing_tables": missing,
                        "behavioral_probe": "not_run"}
            orgs = [str(uuid4()), str(uuid4())]
            deals = [str(uuid4()), str(uuid4())]
            for org, deal in zip(orgs, deals):
                connection.execute(text(
                    "INSERT INTO public.organizations(id,name,slug,created_at,updated_at) "
                    "VALUES (:id,'Recovery probe',:id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"id": org})
                connection.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": org})
                connection.execute(text(
                    "INSERT INTO public.deals(id,name,organization_id,status,created_at,updated_at) "
                    "VALUES (:id,'Recovery probe',:org,'new',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"id": deal, "org": org})
            for org, allowed in zip(orgs, deals):
                connection.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": org})
                visible = connection.execute(text(
                    "SELECT id FROM public.deals WHERE id = ANY(:ids)"
                ), {"ids": deals}).scalars().all()
                if visible != [allowed]:
                    raise ValueError("Cross-tenant read isolation failed")
            connection.execute(text("SELECT set_config('app.current_org', :org, true)"), {"org": orgs[0]})
            rejected = False
            savepoint = connection.begin_nested()
            try:
                connection.execute(text(
                    "INSERT INTO public.deals(id,name,organization_id,status,created_at,updated_at) "
                    "VALUES (:id,'Denied probe',:org,'new',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"id": str(uuid4()), "org": orgs[1]})
            except DBAPIError as exc:
                rejected = getattr(exc.orig, "pgcode", None) == "42501"
            finally:
                savepoint.rollback()
            if not rejected:
                raise ValueError("Cross-tenant write was not rejected by row-level security")
            connection.execute(text("SELECT set_config('app.current_org', '', true)"))
            if connection.execute(text("SELECT count(*) FROM public.deals")).scalar_one() != 0:
                raise ValueError("Unset-tenant default deny failed")
            revisions = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
            return {"passed": True, "migration_revisions": revisions,
                    "protected_tenant_table_count": len(protected),
                    "behavioral_tables_tested": ["deals"],
                    "checks": ["restricted_role", "forced_rls_metadata", "cross_tenant_read", "cross_tenant_write", "default_deny"],
                    "scope": "Isolated restored PostgreSQL only; not proof of snapshot provenance, RPO/RTO or all API authorization"}
        finally:
            transaction.rollback()
