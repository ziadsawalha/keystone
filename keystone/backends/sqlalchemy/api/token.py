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

from keystone.backends.sqlalchemy import get_session, models
from keystone.backends import api
from keystone.models import Token


class TokenAPI(api.BaseTokenAPI):
    @staticmethod
    def transpose(values):
        """ Transposes field names from domain to sql model"""
        if isinstance(api.TENANT, models.Tenant):
            values['tenant_id'] = api.TENANT._uid_to_id(values['tenant_id'])
        if isinstance(api.USER, models.User):
            values['user_id'] = api.USER._uid_to_id(values['user_id'])

    @staticmethod
    def to_model(ref):
        """ Returns Keystone model object based on SQLAlchemy model"""
        if ref:
            if isinstance(api.TENANT, models.Tenant):
                if 'tenant_id' in ref:
                    ref['tenant_id'] = api.TENANT._id_to_uid(ref['tenant_id'])
                elif hasattr(ref, 'tenant_id'):
                    ref.tenant_id = api.TENANT._id_to_uid(ref.tenant_id)

            if isinstance(api.USER, models.User):
                if 'user_id' in ref:
                    ref['user_id'] = api.USER._id_to_uid(ref['user_id'])
                elif hasattr(ref, 'user_id'):
                    ref.user_id = api.USER._id_to_uid(ref.user_id)

            return Token(id=ref.id, user_id=ref.user_id, expires=ref.expires,
                         tenant_id=ref.tenant_id)

    @staticmethod
    def to_model_list(refs):
        return [TokenAPI.to_model(ref) for ref in refs]

    def create(self, values):
        data = values.copy()
        TokenAPI.transpose(data)
        token_ref = models.Token()
        token_ref.update(data)
        token_ref.save()
        return TokenAPI.to_model(token_ref)

    def get(self, id, session=None):
        if not session:
            session = get_session()

        result = session.query(models.Token).filter_by(id=id).first()

        return TokenAPI.to_model(result)

    def delete(self, id, session=None):
        if not session:
            session = get_session()

        with session.begin():
            token_ref = self.get(id, session)
            session.delete(token_ref)

    def get_for_user(self, user_id, session=None):
        if not session:
            session = get_session()

        if isinstance(api.USER, models.User):
            user_id = api.USER._uid_to_id(user_id)

        result = session.query(models.Token).filter_by(
            user_id=user_id, tenant_id=None).order_by("expires desc").first()

        return TokenAPI.to_model(result)

    def get_for_user_by_tenant(self, user_id, tenant_id, session=None):
        if not session:
            session = get_session()

        if isinstance(api.USER, models.User):
            user_id = api.USER._uid_to_id(user_id)

        result = session.query(models.Token).\
            filter_by(user_id=user_id, tenant_id=tenant_id).\
            order_by("expires desc").\
            first()

        return TokenAPI.to_model(result)

    def get_all(self, session=None):
        if not session:
            session = get_session()

        results = session.query(models.Token).all()

        return TokenAPI.to_model_list(results)


def get():
    return TokenAPI()
