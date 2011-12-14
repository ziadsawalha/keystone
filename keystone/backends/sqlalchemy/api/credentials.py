# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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
from keystone.models import Credentials
from keystone.logic.types import fault


class CredentialsAPI(api.BaseCredentialsAPI):
    @staticmethod
    def transpose(values):
        """ Transposes field names from domain to sql model"""
        values['tenant_id'] = api.TENANT._uid_to_id(values['tenant_id'])

    @staticmethod
    def to_model(ref):
        """ Returns Keystone model object based on SQLAlchemy model"""
        if ref:
            tenant_uid = api.TENANT._id_to_uid(ref.tenant_id)

            return Credentials(id=ref.id, user_id=ref.user_id,
                tenant_id=tenant_uid, type=ref.type, key=ref.key, secret=ref.secret)

    @staticmethod
    def to_model_list(refs):
        return [CredentialsAPI.to_model(ref) for ref in refs]

    def create(self, values):
        data = values.copy()
        CredentialsAPI.transpose(data)

        if 'tenant_id' in values:
            if data['tenant_id'] is None and values['tenant_id'] is not None:
                raise fault.ItemNotFoundFault('Invalid tenant id: %s' % \
                                              values['tenant_id'])

        credentials_ref = models.Credentials()
        credentials_ref.update(data)
        credentials_ref.save()

        return CredentialsAPI.to_model(credentials_ref)

    def get(self, id, session=None):
        if not session:
            session = get_session()

        result = session.query(models.Credentials).filter_by(id=id).first()

        return CredentialsAPI.to_model(result)

    def get_by_access(self, access, session=None):
        if not session:
            session = get_session()

        result = session.query(models.Credentials).\
                         filter_by(type="EC2", key=access).first()

        return CredentialsAPI.to_model(result)

    def delete(self, id, session=None):
        if not session:
            session = get_session()

        with session.begin():
            group_ref = self.get(id, session)
            session.delete(group_ref)

def get():
    return CredentialsAPI()
