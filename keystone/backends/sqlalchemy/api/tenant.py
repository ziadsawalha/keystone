# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import uuid

from keystone.backends.sqlalchemy import get_session, models, aliased
from keystone.backends import api
from keystone.models import Tenant


class TenantAPI(api.BaseTenantAPI):
    # pylint: disable=W0221
    @staticmethod
    def transpose(values):
        """ Handles transposing field names from Keystone model to
        sqlalchemy mode

        Differences:
            desc <-> description
            id <-> uid (coming soon)
        """
        if 'id' in values:
            values['uid'] = values['id']
            del values['id']
        if 'description' in values:
            values['desc'] = values['description']
            del values['description']
        if 'enabled' in values:
            if values['enabled'] in [1, 'true', 'True', True]:
                values['enabled'] = 1
            else:
                values['enabled'] = 0

    @staticmethod
    def to_model(ref):
        """ Returns Keystone model object based on SQLAlchemy model"""
        if ref:
            return Tenant(id=ref.uid, description=ref.desc, enabled=bool(ref.enabled), name=ref.name)

    @staticmethod
    def to_model_list(refs):
        return [TenantAPI.to_model(ref) for ref in refs]

    def create(self, values):
        TenantAPI.transpose(values)
        tenant_ref = models.Tenant()
        tenant_ref.update(values)
        tenant_ref.uid = uuid.uuid4().hex
        tenant_ref.save()
        return TenantAPI.to_model(tenant_ref)

    def get(self, id, session=None):
        """Returns a tenant by ID.

        .warning::

            Internally, the provided ID is matched against the ``tenants.UID``,
            not the PK (``tenants.id``) column.

            For PK lookups from within the sqlalchemy backend,
            use ``_get_by_id()`` instead.
        """
        session = session or get_session()

        result = session.query(models.Tenant).filter_by(uid=id).first()

        return TenantAPI.to_model(result)

    def _get_by_id(self, id, session=None):
        """Returns a tenant by ID (PK).

        .warning::

            The provided ID is matched against the PK (``tenants.ID``).

            This is **only** for use within the sqlalchemy backend.
        """
        session = session or get_session()

        return session.query(models.Tenant).filter_by(id=id).first()

    def _id_to_uid(self, id, session=None):
        session = session or get_session()
        tenant = session.query(models.Tenant).filter_by(id=id).first()
        return tenant.uid if tenant else None

    def _uid_to_id(self, uid, session=None):
        session = session or get_session()
        tenant = session.query(models.Tenant).filter_by(uid=uid).first()
        return tenant.id if tenant else None

    def get_by_name(self, name, session=None):
        session = session or get_session()

        result = session.query(models.Tenant).filter_by(name=name).first()

        return TenantAPI.to_model(result)

    def get_all(self, session=None):
        if not session:
            session = get_session()

        results = session.query(models.Tenant).all()

        return TenantAPI.to_model_list(results)

    def tenants_for_user_get_page(self, user, marker, limit, session=None):
        if not session:
            session = get_session()

        user.tenant_id = api.TENANT._uid_to_id(user.tenant_id)

        ura = aliased(models.UserRoleAssociation)
        tenant = aliased(models.Tenant)
        q1 = session.query(tenant).join((ura, ura.tenant_id == tenant.id)).\
            filter(ura.user_id == user.id)
        q2 = session.query(tenant).filter(tenant.id == user.tenant_id)
        q3 = q1.union(q2)
        if marker:
            results = q3.filter("tenant.id>:marker").params(\
                    marker='%s' % marker).order_by(\
                    tenant.id.desc()).limit(limit).all()
        else:
            results = q3.order_by(tenant.id.desc()).limit(limit).all()

        return TenantAPI.to_model_list(results)

    def tenants_for_user_get_page_markers(self, user, marker, limit,
            session=None):
        if not session:
            session = get_session()

        user.tenant_id = api.TENANT._uid_to_id(user.tenant_id)

        ura = aliased(models.UserRoleAssociation)
        tenant = aliased(models.Tenant)
        q1 = session.query(tenant).join((ura, ura.tenant_id == tenant.id)).\
            filter(ura.user_id == user.id)
        q2 = session.query(tenant).filter(tenant.id == user.tenant_id)
        q3 = q1.union(q2)

        first = q3.order_by(\
                            tenant.id).first()
        last = q3.order_by(\
                            tenant.id.desc()).first()
        if first is None:
            return (None, None)
        if marker is None:
            marker = first.id
        next_page = q3.filter(tenant.id > marker).order_by(\
                        tenant.id).limit(limit).all()
        prev_page = q3.filter(tenant.id > marker).order_by(\
                        tenant.id.desc()).limit(int(limit)).all()
        if len(next_page) == 0:
            next_page = last
        else:
            for t in next_page:
                next_page = t
        if len(prev_page) == 0:
            prev_page = first
        else:
            for t in prev_page:
                prev_page = t
        if prev_page.id == marker:
            prev_page = None
        else:
            prev_page = prev_page.id
        if next_page.id == last.id:
            next_page = None
        else:
            next_page = next_page.id
        return (prev_page, next_page)

    def get_page(self, marker, limit, session=None):
        if not session:
            session = get_session()

        if marker:
            return session.query(models.Tenant).filter("id>:marker").params(\
                    marker='%s' % marker).order_by(\
                    models.Tenant.id.desc()).limit(limit).all()
        else:
            return session.query(models.Tenant).order_by(\
                                models.Tenant.id.desc()).limit(limit).all()

    def get_page_markers(self, marker, limit, session=None):
        if not session:
            session = get_session()
        first = session.query(models.Tenant).order_by(\
                            models.Tenant.id).first()
        last = session.query(models.Tenant).order_by(\
                            models.Tenant.id.desc()).first()
        if first is None:
            return (None, None)
        if marker is None:
            marker = first.id
        next_page = session.query(models.Tenant).\
            filter("id > :marker").\
            params(marker='%s' % marker).\
            order_by(models.Tenant.id).\
            limit(limit).\
            all()
        prev_page = session.query(models.Tenant).\
            filter("id < :marker").\
            params(marker='%s' % marker).\
            order_by(models.Tenant.id.desc()).\
            limit(int(limit)).\
            all()
        if len(next_page) == 0:
            next_page = last
        else:
            for t in next_page:
                next_page = t
        if len(prev_page) == 0:
            prev_page = first
        else:
            for t in prev_page:
                prev_page = t
        if prev_page.id == marker:
            prev_page = None
        else:
            prev_page = prev_page.id
        if next_page.id == last.id:
            next_page = None
        else:
            next_page = next_page.id
        return (prev_page, next_page)

    def is_empty(self, id, session=None):
        if not session:
            session = get_session()

        id = self._uid_to_id(id)

        a_user = session.query(models.UserRoleAssociation).filter_by(\
            tenant_id=id).first()
        if a_user != None:
            return False
        a_user = session.query(models.User).filter_by(tenant_id=id).first()
        if a_user != None:
            return False
        return True

    def update(self, id, values, session=None):
        if not session:
            session = get_session()

        id = self._uid_to_id(id)
        data = values.copy()
        TenantAPI.transpose(data)

        with session.begin():
            tenant_ref = self._get_by_id(id, session)
            tenant_ref.update(data)
            tenant_ref.save(session=session)
            return self.get(id, session)

    def delete(self, id, session=None):
        if not session:
            session = get_session()

        id = self._uid_to_id(id)

        with session.begin():
            tenant_ref = self._get_by_id(id, session)
            session.delete(tenant_ref)

    def get_all_endpoints(self, tenant_id, session=None):
        if not session:
            session = get_session()

        if isinstance(api.TENANT, models.Tenant):
            tenant_id = self._uid_to_id(tenant_id)

        endpointTemplates = aliased(models.EndpointTemplates)
        q = session.query(endpointTemplates).\
            filter(endpointTemplates.is_global == True)
        if tenant_id:
            ep = aliased(models.Endpoints)
            q1 = session.query(endpointTemplates).join((ep,
                ep.endpoint_template_id == endpointTemplates.id)).\
                filter(ep.tenant_id == tenant_id)
            q = q.union(q1)
        results = q.all()

        for result in results:
            if isinstance(result, models.Endpoints):
                result.tenant_id = TenantAPI._id_to_uid(result.tenant_id)

        return results

    def get_role_assignments(self, tenant_id, session=None):
        if not session:
            session = get_session()

        tenant_id = TenantAPI._uid_to_id(tenant_id)

        results = session.query(models.UserRoleAssociation).\
            filter_by(tenant_id=tenant_id)

        for result in results:
            result.tenant_id = TenantAPI._id_to_uid(result.tenant_id)

        return results


def get():
    return TenantAPI()
