# Copyright (c) 2010-2011 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime, timedelta
import uuid
import logging

from keystone.logic.types import auth, atom
from keystone.logic.signer import Signer
import keystone.backends as backends
import keystone.backends.api as api
import keystone.backends.models as models
from keystone.logic.types import fault
from keystone.logic.types.tenant import Tenants
from keystone.logic.types.role import Role, Roles
from keystone.logic.types.service import Service, Services
from keystone.logic.types.user import User, User_Update, Users
from keystone.logic.types.endpoint import Endpoint, Endpoints, \
    EndpointTemplate, EndpointTemplates
from keystone.logic.types.credential import Credentials, PasswordCredentials
from keystone.common import wsgi
from keystone import utils
# New imports as we refactor old backend design and models
from keystone.models import Tenant, Token
from keystone.token import Manager as TokenManager
from keystone.tenant import Manager as TenantManager


LOG = logging.getLogger('keystone.logic.service')


def has_admin_role(token_id):
    """ Checks if the token belongs to a user who has Keystone admin
        rights.

        Returns (token, user) if true. False otherwise.

        This is currently assigned using a global role assignment
        (i.e. role assigned without a tenant id). The actual name of the role
        is defined in the config file using the keystone-admin-role setting
    """
    (token, user) = validate_token(token_id)
    initialize_admin_role_identifiers()
    if has_role({"api": api}, user, backends.ADMIN_ROLE_ID):
        return (token, user)
    else:
        return False


def has_service_admin_role(token_id):
    """ Checks if the token belongs to a user who has Keystone Service Admin
        rights. (Note: Keystone Admin rights include Keystone Service Admin).

        Returns (token, user) if true. False otherwise.

        This is currently assigned using a global role assignment
        (i.e. role assigned without a tenant id). The actual name of the role
        is defined in the config file using the keystone-admin-role setting
    """
    (token, user) = validate_token(token_id)
    initialize_admin_role_identifiers()
    if has_role({"api": api}, user,
                backends.SERVICE_ADMIN_ROLE_ID):
        return (token, user)
    else:
        return has_admin_role(token_id)


def validate_admin_token(token_id):
    """ Validates that the token belongs to a user who has Keystone admin
        rights. Raises an Unauthorized exception if not.

        This is currently assigned using a global role assignment
        (i.e. role assigned without a tenant id). The actual name of the role
        is defined in the config file using the keystone-admin-role setting
    """
    result = has_admin_role(token_id)
    if result:
        return result
    else:
        raise fault.UnauthorizedFault(
            "You are not authorized to make this call")


def validate_service_admin_token(token_id):
    """ Validates that the token belongs to a user who has Keystone admin or
        Keystone Service Admin rights. Raises an Unaithorized exception if not.

        These are currently assigned using a global role assignments
        (i.e. roles assigned without a tenant id). The actual name of the roles
        is defined in the config file using the keystone-admin-role and
        keystone-service-admin-role settings
    """
    # Does the user have the Service Admin role
    result = has_service_admin_role(token_id)
    if result:
        return result
    # Does the user have the Admin role (which includes Service Admin rights)
    result = has_admin_role(token_id)
    if result:
        return result

    raise fault.UnauthorizedFault(
        "You are not authorized to make this call")


def initialize_admin_role_identifiers():
    if backends.SERVICE_ADMIN_ROLE_ID is None:
        role = api.ROLE.get_by_name(backends.SERVICE_ADMIN_ROLE_NAME)
        if role:
            backends.SERVICE_ADMIN_ROLE_ID = role.id
        else:
            LOG.warn('No service admin role is defined.')
    if backends.ADMIN_ROLE_ID is None:
        role = api.ROLE.get_by_name(backends.ADMIN_ROLE_NAME)
        if role:
            backends.ADMIN_ROLE_ID = role.id
        else:
            LOG.warn('No service admin role is defined.')


def has_role(env, user, role):
    """Checks if a user has a specific role.

    env:    provides the context
    user:   the user to be checked
    role:   the role to check that the user has
    """
    dbapi = env['api']
    for role_ref in dbapi.ROLE.ref_get_all_global_roles(user.id):
        if (role_ref.role_id == role) \
            and role_ref.tenant_id is None:
            return True
    return False


def is_owner(env, user, object):
    """Checks if a user is the owner of an object.

    This is done by checking if the user id matches the 'owner_id'
    field of the object

    env:    provides the context
    user:   the user to be checked
    role:   the role to check that the user has
    """
    if hasattr(object, 'owner_id'):
        if object.owner_id == user.id:
            return True
    return False


def validate_unscoped_token(token_id, belongs_to=None):
    (token, user) = validate_token(token_id, belongs_to)

    if token.tenant_id:
        raise fault.ForbiddenFault("Expecting unscoped token")

    return (token, user)


def validate_tenant_by_id(tenant_id):
    if not tenant_id:
        raise fault.UnauthorizedFault("Missing tenant id")

    dtenant = api.TENANT.get(tenant_id)

    return validate_tenant(dtenant)


def validate_tenant_by_name(tenant_name):
    if not tenant_name:
        raise fault.UnauthorizedFault("Missing tenant name")

    dtenant = api.TENANT.get_by_name(name=tenant_name)

    return validate_tenant(dtenant)


def get_token_info(token_id):
    """returns token and user object for a token_id"""

    token = None
    user = None
    if token_id:
        token = api.TOKEN.get(token_id)
        if token:
            user = api.USER.get(token.user_id)
    return (token, user)


def get_auth_data(dtoken):
    """returns AuthData object for a token

    AuthData is used for rendering authentication responses
    """
    tenant = None
    endpoints = None

    if dtoken.tenant_id:
        dtenant = api.TENANT.get(dtoken.tenant_id)
        tenant = auth.Tenant(id=dtenant.id, name=dtenant.name)

        endpoints = api.TENANT.get_all_endpoints(dtoken.tenant_id)

    token = auth.Token(dtoken.expires, dtoken.id, tenant)

    duser = api.USER.get(dtoken.user_id)

    ts = []
    if dtoken.tenant_id:
        drole_refs = api.ROLE.ref_get_all_tenant_roles(duser.id,
            dtoken.tenant_id)
        for drole_ref in drole_refs:
            drole = api.ROLE.get(drole_ref.role_id)
            ts.append(Role(drole_ref.role_id, drole.name,
                drole.desc, None, drole_ref.tenant_id))
    drole_refs = api.ROLE.ref_get_all_global_roles(duser.id)
    for drole_ref in drole_refs:
        drole = api.ROLE.get(drole_ref.role_id)
        ts.append(Role(drole_ref.role_id, drole.name,
            drole.desc, None, drole_ref.tenant_id))
    user = auth.User(duser.id, duser.name, None, None, Roles(ts, []))
    if has_service_admin_role(token.id):
        # Privileged users see the adminURL as well
        url_types = ['admin', 'internal', 'public']
    else:
        url_types = ['internal', 'public']
    return auth.AuthData(token, user, endpoints, url_types=url_types)


def get_validate_data(dtoken, duser):
    """return ValidateData object for a token/user pair"""
    tenant = None
    if dtoken.tenant_id:
        dtenant = api.TENANT.get(dtoken.tenant_id)
        tenant = auth.Tenant(id=dtenant.id, name=dtenant.name)

    token = auth.Token(dtoken.expires, dtoken.id, tenant)

    ts = []
    if dtoken.tenant_id:
        drole_refs = api.ROLE.ref_get_all_tenant_roles(duser.id,
            dtoken.tenant_id)
        for drole_ref in drole_refs:
            drole = api.ROLE.get(drole_ref.role_id)
            ts.append(Role(drole_ref.role_id, drole.name,
                None, drole_ref.tenant_id))
    drole_refs = api.ROLE.ref_get_all_global_roles(duser.id)
    for drole_ref in drole_refs:
        drole = api.ROLE.get(drole_ref.role_id)
        ts.append(Role(drole_ref.role_id, drole.name,
            None, drole_ref.tenant_id))

    # Also get the user's tenant's name
    tenant_name = None
    if duser.tenant_id:
        utenant = api.TENANT.get(duser.tenant_id)
        tenant_name = utenant.name

    user = auth.User(duser.id, duser.name, duser.tenant_id,
        tenant_name, Roles(ts, []))

    return auth.ValidateData(token, user)


def validate_tenant(dtenant):
    if not dtenant:
        raise fault.UnauthorizedFault("Tenant not found")

    if dtenant.enabled is None or \
            str(dtenant.enabled).lower() not in ['1', 'true']:
        raise fault.TenantDisabledFault("Tenant %s has been disabled!"
            % dtenant.id)

    return dtenant


def validate_token(token_id, belongs_to=None, is_check_token=None):
    """
    Method to validate a token.
    token_id -- id of the token that needs to be validated.
    belongs_to -- optional tenant_id to check whether the token is
    mapped to a specific tenant.
    is_check_token -- optional argument that tells whether
    we check the existence of a Token using another Token
    to authenticate. This value decides the faults that are to be thrown.
    """
    if not token_id:
        raise fault.UnauthorizedFault("Missing token")

    (token, user) = get_token_info(token_id)

    if not token:
        if is_check_token:
            raise fault.ItemNotFoundFault("Token does not exist.")
        else:
            raise fault.UnauthorizedFault(
                "Bad token, please reauthenticate")

    if token.expires < datetime.now():
        if is_check_token:
            raise fault.ItemNotFoundFault("Token expired, please renew.")
        else:
            raise fault.ForbiddenFault("Token expired, please renew.")

    if not user.enabled:
        raise fault.UserDisabledFault("User %s has been disabled!"
            % user.id)

    if user.tenant_id:
        validate_tenant_by_id(user.tenant_id)

    if token.tenant_id:
        validate_tenant_by_id(token.tenant_id)

    if belongs_to and unicode(token.tenant_id) != unicode(belongs_to):
        raise fault.UnauthorizedFault("Unauthorized on this tenant")

    return (token, user)


class IdentityService(object):
    """Implements the Identity service

    This class handles all logic of routing requests to the correct
    backend as well as validating incoming/outgoing data
    """

    def __init__(self, options):
        """ Initialize

        Loads all necessary backends to handle incoming requests.
        """
        backends.configure_backends(options)
        self.token_manager = TokenManager(options)
        self.tenant_manager = TenantManager(options)

    #
    #  Token Operations
    #
    def authenticate(self, auth_request):
        # Check auth_with_password_credentials
        if not isinstance(auth_request, auth.AuthWithPasswordCredentials):
            raise fault.BadRequestFault(
                "Expecting auth_with_password_credentials!")

        def validate(duser):
            return api.USER.check_password(duser, auth_request.password)

        if auth_request.tenant_name:
            dtenant = validate_tenant_by_name(auth_request.tenant_name)
            auth_request.tenant_id = dtenant.id
        elif auth_request.tenant_id:
            dtenant = validate_tenant_by_id(auth_request.tenant_id)

        user = api.USER.get_by_name(auth_request.username)
        if not user:
            raise fault.UnauthorizedFault("Unauthorized")

        return self._authenticate(
            validate, user.id, auth_request.tenant_id)

    def authenticate_with_unscoped_token(self, auth_request):
        # Check auth_with_unscoped_token
        if not isinstance(auth_request, auth.AuthWithUnscopedToken):
            raise fault.BadRequestFault("Expecting auth_with_unscoped_token!")

        # We *should* check for an unscoped token here, but as long as
        # POST /tokens w/ credentials auto-scopes to User.tenantId, users can't
        # reach this flow.
        # _token, user = validate_unscoped_token(auth_request.token_id)
        _token, user = validate_token(auth_request.token_id)

        if auth_request.tenant_name:
            dtenant = validate_tenant_by_name(auth_request.tenant_name)
            auth_request.tenant_id = dtenant.id
        elif auth_request.tenant_id:
            dtenant = validate_tenant_by_id(auth_request.tenant_id)

        def validate(duser):
            # The user is already authenticated
            return True
        return self._authenticate(validate, user.id,
                                             auth_request.tenant_id)

    def authenticate_ec2(self, credentials):
        # Check credentials
        if not isinstance(credentials, auth.Ec2Credentials):
            raise fault.BadRequestFault("Expecting Ec2 Credentials!")

        creds = api.CREDENTIALS.get_by_access(credentials.access)
        if not creds:
            raise fault.UnauthorizedFault("No credentials found for %s"
                                          % credentials.access)

        def validate(duser):
            signer = Signer(creds.secret)
            signature = signer.generate(credentials)
            if signature == credentials.signature:
                return True
            # NOTE(vish): Some libraries don't use the port when signing
            #             requests, so try again without port.
            if ':' in credentials.host:
                hostname, _port = credentials.host.split(":")
                credentials.host = hostname
                signature = signer.generate(credentials)
                return signature == credentials.signature
            return False
        return self._authenticate(validate, creds.user_id,
                                             creds.tenant_id)

    def _authenticate(self, validate, user_id, tenant_id=None):
        if tenant_id:
            duser = api.USER.get_by_tenant(user_id, tenant_id)
            if duser is None:
                raise fault.UnauthorizedFault("Unauthorized on this tenant")
        else:
            duser = api.USER.get(user_id)
            if duser is None:
                raise fault.UnauthorizedFault("Unauthorized")

        if not duser.enabled:
            raise fault.UserDisabledFault("Your account has been disabled")

        if not validate(duser):
            raise fault.UnauthorizedFault("Unauthorized")

        # use user's default tenant_id if one is not specified
        tenant_id = tenant_id or duser.tenant_id

        # check for an existing token
        dtoken = api.TOKEN.get_for_user_by_tenant(duser.id, tenant_id)

        if not dtoken or dtoken.expires < datetime.now():
            # Create new token
            dtoken = Token()
            dtoken.id = str(uuid.uuid4())
            dtoken.user_id = duser.id
            dtoken.tenant_id = tenant_id
            dtoken.expires = datetime.now() + timedelta(days=1)
            dtoken = api.TOKEN.create(dtoken)
        return get_auth_data(dtoken)

    def validate_token(self, admin_token, token_id, belongs_to=None):
        validate_service_admin_token(admin_token)
        (token, user) = validate_token(token_id, belongs_to, True)
        return get_validate_data(token, user)

    def revoke_token(self, admin_token, token_id):
        validate_admin_token(admin_token)

        dtoken = api.TOKEN.get(token_id)
        if not dtoken:
            raise fault.ItemNotFoundFault("Token not found")

        api.TOKEN.delete(token_id)

    def get_endpoints_for_token(self, admin_token,
            token_id, marker, limit, url,):
        validate_service_admin_token(admin_token)
        dtoken = api.TOKEN.get(token_id)
        if not dtoken:
            raise fault.ItemNotFoundFault("Token not found")
        if not dtoken.tenant_id:
            raise fault.ItemNotFoundFault("Token not mapped to any tenant.")
        return self.fetch_tenant_endpoints(
            marker, limit, url, dtoken.tenant_id)

    #
    #   Tenant Operations
    #
    def create_tenant(self, admin_token, tenant):
        validate_admin_token(admin_token)

        if not isinstance(tenant, Tenant):
            raise fault.BadRequestFault("Expecting a Tenant")

        utils.check_empty_string(tenant.name, "Expecting a unique Tenant Name")
        if api.TENANT.get_by_name(tenant.name) is not None:
            raise fault.TenantConflictFault(
                "A tenant with that name already exists")

        dtenant = Tenant()
        dtenant.name = tenant.name
        dtenant.description = tenant.description
        dtenant.enabled = tenant.enabled
        return api.TENANT.create(dtenant)

    def get_tenants(self, admin_token, marker, limit, url,
                    is_service_operation=False):
        """Fetch tenants for either an admin or service operation."""
        ts = []

        if is_service_operation:
            # Check regular token validity.
            (_token, user) = validate_token(admin_token, False)

            # Return tenants specific to user
            dtenants = api.TENANT.tenants_for_user_get_page(
                user, marker, limit)
            prev_page, next_page = api.TENANT.\
                tenants_for_user_get_page_markers(user, marker, limit)
        else:
            #Check Admin Token
            (_token, user) = validate_admin_token(admin_token)
            # Return all tenants
            dtenants = api.TENANT.get_page(marker, limit)
            prev_page, next_page = api.TENANT.get_page_markers(marker, limit)

        for dtenant in dtenants:
            t = Tenant(id=dtenant.id, name=dtenant.name,
                description=dtenant.desc, enabled=dtenant.enabled)
            ts.append(t)

        links = self.get_links(url, prev_page, next_page, limit)
        return Tenants(ts, links)

    def get_tenant(self, admin_token, tenant_id):
        validate_admin_token(admin_token)

        dtenant = api.TENANT.get(tenant_id)
        if not dtenant:
            raise fault.ItemNotFoundFault("The tenant could not be found")
        return Tenant(dtenant.id, dtenant.name, dtenant.desc, dtenant.enabled)

    def get_tenant_by_name(self, admin_token, tenant_name):
        validate_admin_token(admin_token)

        dtenant = api.TENANT.get_by_name(tenant_name)
        if not dtenant:
            raise fault.ItemNotFoundFault("The tenant could not be found")
        return Tenant(dtenant.id, dtenant.name, dtenant.desc, dtenant.enabled)

    def update_tenant(self, admin_token, tenant_id, tenant):
        validate_admin_token(admin_token)

        if not isinstance(tenant, Tenant):
            raise fault.BadRequestFault("Expecting a Tenant")

        dtenant = api.TENANT.get(tenant_id)
        if dtenant is None:
            raise fault.ItemNotFoundFault("The tenant could not be found")

        utils.check_empty_string(tenant.name, "Expecting a unique Tenant Name")

        if tenant.name != dtenant.name and api.TENANT.get_by_name(tenant.name):
            raise fault.TenantConflictFault(
                "A tenant with that name already exists")
        values = {'desc': tenant.description, 'enabled': tenant.enabled,
                  'name': tenant.name}
        api.TENANT.update(tenant_id, values)
        dtenant = api.TENANT.get(tenant_id)
        return Tenant(id=dtenant.id, name=dtenant.name,
            description=dtenant.desc, enabled=dtenant.enabled)

    def delete_tenant(self, admin_token, tenant_id):
        validate_admin_token(admin_token)

        dtenant = api.TENANT.get(tenant_id)
        if dtenant is None:
            raise fault.ItemNotFoundFault("The tenant could not be found")

        if not api.TENANT.is_empty(tenant_id):
            raise fault.ForbiddenFault("You may not delete a tenant that "
                                       "contains get_users")

        api.TENANT.delete(dtenant.id)
        return None

    #
    #   User Operations
    #
    def create_user(self, admin_token, user):
        validate_admin_token(admin_token)

        self.validate_and_fetch_user_tenant(user.tenant_id)

        if not isinstance(user, User):
            raise fault.BadRequestFault("Expecting a User")

        utils.check_empty_string(user.name,
                "Expecting a unique user Name")

        if api.USER.get_by_name(user.name):
            raise fault.UserConflictFault(
                "A user with that name already exists")

        if api.USER.get_by_email(user.email):
            raise fault.EmailConflictFault(
                "A user with that email already exists")

        duser = models.User()
        duser.name = user.name
        duser.password = user.password
        duser.email = user.email
        duser.enabled = user.enabled
        duser.tenant_id = user.tenant_id
        duser = api.USER.create(duser)
        user.id = duser.id
        return user

    def validate_and_fetch_user_tenant(self, tenant_id):
        if tenant_id:
            dtenant = api.TENANT.get(tenant_id)
            if dtenant is None:
                raise fault.ItemNotFoundFault("The tenant is not found")
            elif not dtenant.enabled:
                raise fault.TenantDisabledFault(
                    "Your account has been disabled")
            return dtenant

    def get_tenant_users(self, admin_token, tenant_id,
        role_id, marker, limit, url):
        validate_admin_token(admin_token)

        if tenant_id is None:
            raise fault.BadRequestFault("Expecting a Tenant Id")
        dtenant = api.TENANT.get(tenant_id)
        if dtenant is  None:
            raise fault.ItemNotFoundFault("The tenant not found")
        if not dtenant.enabled:
            raise fault.TenantDisabledFault("Your account has been disabled")
        if role_id:
            if not api.ROLE.get(role_id):
                raise fault.ItemNotFoundFault("The role not found")
        ts = []
        dtenantusers = api.USER.users_get_by_tenant_get_page(
            tenant_id, role_id, marker, limit)
        for dtenantuser in dtenantusers:
            ts.append(User(None, dtenantuser.id, dtenantuser.name, tenant_id,
                           dtenantuser.email, dtenantuser.enabled,
                           dtenantuser.tenant_roles if hasattr(dtenantuser,
                                                    "tenant_roles") else None))
        links = []
        if ts.__len__():
            prev, next = api.USER.users_get_by_tenant_get_page_markers(
                    tenant_id, role_id, marker, limit)
            links = self.get_links(url, prev, next, limit)
        return Users(ts, links)

    def get_users(self, admin_token, marker, limit, url):
        validate_admin_token(admin_token)
        ts = []
        dusers = api.USER.users_get_page(marker, limit)
        for duser in dusers:
            ts.append(User(None, duser.id, duser.name, duser.tenant_id,
                                   duser.email, duser.enabled))
        links = []
        if ts.__len__():
            prev, next = api.USER.users_get_page_markers(marker, limit)
            links = self.get_links(url, prev, next, limit)
        return Users(ts, links)

    def get_user(self, admin_token, user_id):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        return User_Update(id=duser.id, tenant_id=duser.tenant_id,
                email=duser.email, enabled=duser.enabled, name=duser.name)

    def get_user_by_name(self, admin_token, user_name):
        validate_admin_token(admin_token)
        duser = api.USER.get_by_name(user_name)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        return User_Update(id=duser.id, tenant_id=duser.tenant_id,
                email=duser.email, enabled=duser.enabled, name=duser.name)

    def update_user(self, admin_token, user_id, user):
        validate_admin_token(admin_token)

        duser = api.USER.get(user_id)

        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        if not isinstance(user, User):
            raise fault.BadRequestFault("Expecting a User")

        utils.check_empty_string(user.name,
                "Expecting a unique username")

        if user.name != duser.name and \
          api.USER.get_by_name(user.name):
            raise fault.UserConflictFault(
                "A user with that name already exists")

        if user.email != duser.email and \
                api.USER.get_by_email(user.email) is not None:
            raise fault.EmailConflictFault("Email already exists")

        values = {'email': user.email, 'name': user.name}
        api.USER.update(user_id, values)
        duser = api.USER.user_get_update(user_id)
        return User(duser.password, duser.id, duser.name, duser.tenant_id,
            duser.email, duser.enabled)

    def set_user_password(self, admin_token, user_id, user):
        validate_admin_token(admin_token)

        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        if not isinstance(user, User):
            raise fault.BadRequestFault("Expecting a User")

        duser = api.USER.get(user_id)
        if duser is None:
            raise fault.ItemNotFoundFault("The user could not be found")

        values = {'password': user.password}

        api.USER.update(user_id, values)

        return User_Update(password=user.password)

    def enable_disable_user(self, admin_token, user_id, user):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        if not isinstance(user, User):
            raise fault.BadRequestFault("Expecting a User")

        values = {'enabled': user.enabled}

        api.USER.update(user_id, values)

        duser = api.USER.get(user_id)

        return User_Update(enabled=user.enabled)

    def set_user_tenant(self, admin_token, user_id, user):
        validate_admin_token(admin_token)

        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        if not isinstance(user, User):
            raise fault.BadRequestFault("Expecting a User")

        self.validate_and_fetch_user_tenant(user.tenant_id)
        values = {'tenant_id': user.tenant_id}
        api.USER.update(user_id, values)
        return User_Update(tenant_id=user.tenant_id)

    def delete_user(self, admin_token, user_id):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        dtenant = api.TENANT.get(duser.tenant_id)
        if dtenant != None:
            api.USER.delete_tenant_user(user_id, dtenant.id)
        else:
            api.USER.delete(user_id)
        return None

    def create_role(self, admin_token, role):
        user = validate_service_admin_token(admin_token)[1]

        if not isinstance(role, Role):
            raise fault.BadRequestFault("Expecting a Role")

        utils.check_empty_string(role.name, "Expecting a Role name")

        if api.ROLE.get(role.name) != None:
            raise fault.RoleConflictFault(
                "A role with that name '" + role.name + "' already exists")

        #Check if the role name includes an embedded service: in it
        #if so, verify the service exists
        if role.service_id is None:
            split = role.name.split(":")
            if isinstance(split, list) and len(split) > 1:
                service_name = split[0]
                service = api.SERVICE.get_by_name(service_name)
                if service is None:
                    raise fault.BadRequestFault(
                        "A service with the name %s doesn't exist." \
                        % service_name)
                role.service_id = service.id

        # Check ownership of the service (or overriding admin rights)
        if role.service_id:
            service = api.SERVICE.get(role.service_id)
            if service is None:
                raise fault.BadRequestFault(
                    "A service with that id doesn't exist.")
            if not role.name.startswith(service.name + ":"):
                raise fault.BadRequestFault(
                    "Role should begin with service name '" +
                        service.name + ":'")
            if not is_owner({"api": api}, user, service):
                if not has_admin_role(admin_token):
                    raise fault.UnauthorizedFault(
                        "You do not have ownership of the '%s' service" \
                        % service.name)

        drole = models.Role()
        drole.name = role.name
        drole.desc = role.description
        drole.service_id = role.service_id
        drole = api.ROLE.create(drole)
        role.id = drole.id
        return role

    def get_roles(self, admin_token, marker, limit, url):
        validate_service_admin_token(admin_token)

        ts = []
        droles = api.ROLE.get_page(marker, limit)
        for drole in droles:
            ts.append(Role(drole.id, drole.name, drole.desc, drole.service_id))
        prev, next = api.ROLE.get_page_markers(marker, limit)
        links = self.get_links(url, prev, next, limit)
        return Roles(ts, links)

    def get_role(self, admin_token, role_id):
        validate_service_admin_token(admin_token)

        drole = api.ROLE.get(role_id)
        if not drole:
            raise fault.ItemNotFoundFault("The role could not be found")
        return Role(drole.id, drole.name, drole.desc, drole.service_id)

    def get_role_by_name(self, admin_token, role_name):
        validate_service_admin_token(admin_token)

        drole = api.ROLE.get_by_name(role_name)
        if not drole:
            raise fault.ItemNotFoundFault("The role could not be found")
        return Role(drole.id, drole.name, drole.desc, drole.service_id)

    def delete_role(self, admin_token, role_id):
        user = validate_service_admin_token(admin_token)[1]

        drole = api.ROLE.get(role_id)
        if not drole:
            raise fault.ItemNotFoundFault("The role could not be found")

        # Check ownership of the service (or overriding admin rights)
        if drole.service_id:
            service = api.SERVICE.get(drole.service_id)
            if service:
                if not is_owner({"api": api}, user, service):
                    if not has_admin_role(admin_token):
                        raise fault.UnauthorizedFault(
                            "You do not have ownership of the '%s' service" \
                            % service.name)

        role_refs = api.ROLE.ref_get_by_role(role_id)
        if role_refs != None:
            for role_ref in role_refs:
                api.ROLE.ref_delete(role_ref.id)
        api.ROLE.delete(role_id)

    def add_role_to_user(self, admin_token,
        user_id, role_id, tenant_id=None):
        validate_service_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        drole = api.ROLE.get(role_id)
        if drole is None:
            raise fault.ItemNotFoundFault("The role not found")
        if tenant_id != None:
            dtenant = api.TENANT.get(tenant_id)
            if dtenant is None:
                raise fault.ItemNotFoundFault("The tenant not found")

        drole_ref = api.ROLE.ref_get_by_user(user_id, role_id, tenant_id)
        if drole_ref is not None:
            raise fault.RoleConflictFault(
                "This role is already mapped to the user.")

        drole_ref = models.UserRoleAssociation()
        drole_ref.user_id = duser.id
        drole_ref.role_id = drole.id
        if tenant_id != None:
            drole_ref.tenant_id = dtenant.id
        api.USER.user_role_add(drole_ref)

    def remove_role_from_user(self, admin_token,
        user_id, role_id, tenant_id=None):
        validate_service_admin_token(admin_token)
        print user_id, role_id, tenant_id
        drole_ref = api.ROLE.ref_get_by_user(user_id, role_id, tenant_id)
        if drole_ref is None:
            raise fault.ItemNotFoundFault(
                "This role is not mapped to the user.")
        api.ROLE.ref_delete(drole_ref.id)

    def get_user_roles(self, admin_token, marker,
        limit, url, user_id, tenant_id):
        validate_service_admin_token(admin_token)
        duser = api.USER.get(user_id)

        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        if tenant_id is not None:
            dtenant = api.TENANT.get(tenant_id)
            if not dtenant:
                raise fault.ItemNotFoundFault("The tenant could not be found.")
        ts = []
        drole_refs = api.ROLE.ref_get_page(marker, limit, user_id, tenant_id)
        for drole_ref in drole_refs:
            drole = api.ROLE.get(drole_ref.role_id)
            ts.append(Role(drole.id, drole.name,
                    drole.desc, drole.service_id))
        prev, next = api.ROLE.ref_get_page_markers(
            user_id, tenant_id, marker, limit)
        links = self.get_links(url, prev, next, limit)
        return Roles(ts, links)

    def add_endpoint_template(self, admin_token, endpoint_template):
        user = validate_service_admin_token(admin_token)[1]

        if not isinstance(endpoint_template, EndpointTemplate):
            raise fault.BadRequestFault("Expecting a EndpointTemplate")

        utils.check_empty_string(endpoint_template.name,
                "Expecting Endpoint Template name.")
        utils.check_empty_string(endpoint_template.type,
                "Expecting Endpoint Template type.")

        dservice = api.SERVICE.get_by_name_and_type(
            endpoint_template.name,
            endpoint_template.type)
        if dservice is None:
            raise fault.BadRequestFault(
                    "A service with that name and type doesn't exist.")

        # Check ownership of the service (or overriding admin rights)
        if not is_owner({"api": api}, user, dservice):
            if not has_admin_role(admin_token):
                raise fault.UnauthorizedFault(
                    "You do not have ownership of the '%s' service" \
                    % dservice.name)

        dendpoint_template = models.EndpointTemplates()
        dendpoint_template.region = endpoint_template.region
        dendpoint_template.service_id = dservice.id
        dendpoint_template.public_url = endpoint_template.public_url
        dendpoint_template.admin_url = endpoint_template.admin_url
        dendpoint_template.internal_url = endpoint_template.internal_url
        dendpoint_template.enabled = endpoint_template.enabled
        dendpoint_template.is_global = endpoint_template.is_global
        dendpoint_template.version_id = endpoint_template.version_id
        dendpoint_template.version_list = endpoint_template.version_list
        dendpoint_template.version_info = endpoint_template.version_info
        dendpoint_template = api.ENDPOINT_TEMPLATE.create(dendpoint_template)
        endpoint_template.id = dendpoint_template.id
        return endpoint_template

    def modify_endpoint_template(self, admin_token, endpoint_template_id,
                                 endpoint_template):
        user = validate_service_admin_token(admin_token)[1]

        if not isinstance(endpoint_template, EndpointTemplate):
            raise fault.BadRequestFault("Expecting a EndpointTemplate")
        dendpoint_template = api.ENDPOINT_TEMPLATE.get(endpoint_template_id)
        if not dendpoint_template:
            raise fault.ItemNotFoundFault(
                "The endpoint template could not be found")

        #Check if the passed service exist.
        utils.check_empty_string(endpoint_template.name,
            "Expecting Endpoint Template name.")
        utils.check_empty_string(endpoint_template.type,
            "Expecting Endpoint Template type.")

        dservice = api.SERVICE.get(dendpoint_template.service_id)
        if not dservice:
            raise fault.BadRequestFault(
                    "A service with that name and type doesn't exist.")

        # Check ownership of the service (or overriding admin rights)
        if not is_owner({"api": api}, user, dservice):
            if not has_admin_role(admin_token):
                raise fault.UnauthorizedFault(
                    "You do not have ownership of the '%s' service" \
                    % dservice.name)

        dendpoint_template.region = endpoint_template.region
        dendpoint_template.service_id = dservice.id
        dendpoint_template.public_url = endpoint_template.public_url
        dendpoint_template.admin_url = endpoint_template.admin_url
        dendpoint_template.internal_url = endpoint_template.internal_url
        dendpoint_template.enabled = endpoint_template.enabled
        dendpoint_template.is_global = endpoint_template.is_global
        dendpoint_template.version_id = endpoint_template.version_id
        dendpoint_template.version_list = endpoint_template.version_list
        dendpoint_template.version_info = endpoint_template.version_info
        dendpoint_template = api.ENDPOINT_TEMPLATE.update(
            endpoint_template_id, dendpoint_template)
        return EndpointTemplate(
            dendpoint_template.id,
            dendpoint_template.region,
            dservice.name,
            dservice.type,
            dendpoint_template.public_url,
            dendpoint_template.admin_url,
            dendpoint_template.internal_url,
            dendpoint_template.enabled,
            dendpoint_template.is_global,
            dendpoint_template.version_id,
            dendpoint_template.version_list,
            dendpoint_template.version_info
            )

    def delete_endpoint_template(self, admin_token, endpoint_template_id):
        user = validate_service_admin_token(admin_token)[1]
        dendpoint_template = api.ENDPOINT_TEMPLATE.get(endpoint_template_id)
        if not dendpoint_template:
            raise fault.ItemNotFoundFault(
                "The endpoint template could not be found")

        dservice = api.SERVICE.get(dendpoint_template.service_id)
        if dservice:
            # Check ownership of the service (or overriding admin rights)
            if not is_owner({"api": api}, user, dservice):
                if not has_admin_role(admin_token):
                    raise fault.UnauthorizedFault(
                        "You do not have ownership of the '%s' service" \
                        % dservice.name)
        else:
            # Cannot verify service ownership, so verify full admin rights
            if not has_admin_role(admin_token):
                raise fault.UnauthorizedFault(
                    "You do not have ownership of the '%s' service" \
                    % dservice.name)

        #Delete Related endpoints
        endpoints = api.ENDPOINT_TEMPLATE.\
            endpoint_get_by_endpoint_template(endpoint_template_id)
        if endpoints != None:
            for endpoint in endpoints:
                api.ENDPOINT_TEMPLATE.endpoint_delete(endpoint.id)
        api.ENDPOINT_TEMPLATE.delete(endpoint_template_id)

    def get_endpoint_templates(self, admin_token, marker, limit, url):
        validate_service_admin_token(admin_token)
        dendpoint_templates = api.ENDPOINT_TEMPLATE.get_page(marker, limit)
        ts = self.transform_endpoint_templates(dendpoint_templates)
        prev, next = api.ENDPOINT_TEMPLATE.get_page_markers(marker, limit)
        links = self.get_links(url, prev, next, limit)
        return EndpointTemplates(ts, links)

    def get_endpoint_templates_by_service(self, admin_token,
        service_id, marker, limit, url):
        validate_service_admin_token(admin_token)
        dservice = api.SERVICE.get(service_id)
        if dservice is None:
            raise fault.ItemNotFoundFault(
                "No service with the id %s found." % service_id)
        dendpoint_templates = api.ENDPOINT_TEMPLATE.\
            get_by_service_get_page(service_id, marker, limit)
        ts = self.transform_endpoint_templates(dendpoint_templates)
        prev, next = api.ENDPOINT_TEMPLATE.\
            get_by_service_get_page_markers(service_id, marker, limit)
        links = self.get_links(url, prev, next, limit)
        return EndpointTemplates(ts, links)

    def transform_endpoint_templates(self, dendpoint_templates):
        ts = []
        for dendpoint_template in dendpoint_templates:
            dservice = api.SERVICE.get(dendpoint_template.service_id)
            ts.append(EndpointTemplate(
                dendpoint_template.id,
                dendpoint_template.region,
                dservice.name,
                dservice.type,
                dendpoint_template.public_url,
                dendpoint_template.admin_url,
                dendpoint_template.internal_url,
                dendpoint_template.enabled,
                dendpoint_template.is_global,
                dendpoint_template.version_id,
                dendpoint_template.version_list,
                dendpoint_template.version_info
                ))
        return ts

    def get_endpoint_template(self, admin_token, endpoint_template_id):
        validate_service_admin_token(admin_token)

        dendpoint_template = api.ENDPOINT_TEMPLATE.get(endpoint_template_id)
        if not dendpoint_template:
            raise fault.ItemNotFoundFault(
                "The endpoint template could not be found")
        dservice = api.SERVICE.get(dendpoint_template.service_id)
        return EndpointTemplate(
            dendpoint_template.id,
            dendpoint_template.region,
            dservice.name,
            dservice.type,
            dendpoint_template.public_url,
            dendpoint_template.admin_url,
            dendpoint_template.internal_url,
            dendpoint_template.enabled,
            dendpoint_template.is_global,
            dendpoint_template.version_id,
            dendpoint_template.version_list,
            dendpoint_template.version_info
            )

    def get_tenant_endpoints(self, admin_token, marker, limit, url, tenant_id):
        validate_service_admin_token(admin_token)
        return self.fetch_tenant_endpoints(marker, limit,
                                                      url, tenant_id)

    def fetch_tenant_endpoints(self, marker, limit, url, tenant_id):
        if tenant_id is None:
            raise fault.BadRequestFault("Expecting a Tenant Id")

        if api.TENANT.get(tenant_id) is None:
            raise fault.ItemNotFoundFault("The tenant not found")

        ts = []

        dtenant_endpoints = \
            api.ENDPOINT_TEMPLATE.\
                endpoint_get_by_tenant_get_page(
                    tenant_id, marker, limit)
        for dtenant_endpoint in dtenant_endpoints:
            dendpoint_template = api.ENDPOINT_TEMPLATE.get(
                dtenant_endpoint.endpoint_template_id)
            dservice = api.SERVICE.get(dendpoint_template.service_id)
            ts.append(Endpoint(
                            dtenant_endpoint.id,
                            dtenant_endpoint.tenant_id,
                            dendpoint_template.region,
                            dservice.name,
                            dservice.type,
                            dendpoint_template.public_url,
                            dendpoint_template.admin_url,
                            dendpoint_template.internal_url,
                            dendpoint_template.version_id,
                            dendpoint_template.version_list,
                            dendpoint_template.version_info
                            ))
        links = []
        if ts.__len__():
            prev, next = \
                api.ENDPOINT_TEMPLATE.endpoint_get_by_tenant_get_page_markers(
                    tenant_id, marker, limit)
            links = self.get_links(url, prev, next, limit)
        return Endpoints(ts, links)

    def create_endpoint_for_tenant(self, admin_token,
                                     tenant_id, endpoint_template):
        validate_service_admin_token(admin_token)
        utils.check_empty_string(tenant_id, "Expecting a Tenant Id.")
        if api.TENANT.get(tenant_id) is None:
            raise fault.ItemNotFoundFault("The tenant not found")

        dendpoint_template = api.ENDPOINT_TEMPLATE.get(endpoint_template.id)
        if not dendpoint_template:
            raise fault.ItemNotFoundFault(
                "The endpoint template could not be found")
        dendpoint = models.Endpoints()
        dendpoint.tenant_id = tenant_id
        dendpoint.endpoint_template_id = endpoint_template.id
        dendpoint = api.ENDPOINT_TEMPLATE.endpoint_add(dendpoint)
        dservice = api.SERVICE.get(dendpoint_template.service_id)
        dendpoint = Endpoint(
                            dendpoint.id,
                            dendpoint.tenant_id,
                            dendpoint_template.region,
                            dservice.name,
                            dservice.type,
                            dendpoint_template.public_url,
                            dendpoint_template.admin_url,
                            dendpoint_template.internal_url,
                            dendpoint_template.version_id,
                            dendpoint_template.version_list,
                            dendpoint_template.version_info
                            )
        return dendpoint

    def delete_endpoint(self, admin_token, endpoint_id):
        validate_service_admin_token(admin_token)
        if api.ENDPOINT_TEMPLATE.get(endpoint_id) is None:
            raise fault.ItemNotFoundFault("The Endpoint is not found.")
        api.ENDPOINT_TEMPLATE.endpoint_delete(endpoint_id)
        return None

    #Service Operations
    def create_service(self, admin_token, service):
        validate_service_admin_token(admin_token)

        if not isinstance(service, Service):
            raise fault.BadRequestFault("Expecting a Service")

        if api.SERVICE.get_by_name(service.name) != None:
            raise fault.ServiceConflictFault(
                "A service with that name already exists")

        user = validate_token(admin_token)[1]

        dservice = models.Service()
        dservice.name = service.name
        dservice.type = service.type
        dservice.desc = service.description
        dservice.owner_id = user.id
        dservice = api.SERVICE.create(dservice)
        service.id = dservice.id

        return service

    def get_services(self, admin_token, marker, limit, url):
        validate_service_admin_token(admin_token)

        ts = []
        dservices = api.SERVICE.get_page(marker, limit)
        for dservice in dservices:
            ts.append(Service(dservice.id, dservice.name, dservice.type,
                dservice.desc))
        prev, next = api.SERVICE.get_page_markers(marker, limit)
        links = self.get_links(url, prev, next, limit)
        return Services(ts, links)

    def get_service(self, admin_token, service_id):
        validate_service_admin_token(admin_token)

        dservice = api.SERVICE.get(service_id)
        if not dservice:
            raise fault.ItemNotFoundFault("The service could not be found")
        return Service(dservice.id, dservice.name, dservice.type,
            dservice.desc)

    def get_service_by_name(self, admin_token, service_name):
        validate_service_admin_token(admin_token)
        dservice = api.SERVICE.get_by_name(service_name)
        if not dservice:
            raise fault.ItemNotFoundFault("The service could not be found")
        return Service(dservice.id, dservice.name, dservice.type,
            dservice.desc)

    def delete_service(self, admin_token, service_id):
        validate_service_admin_token(admin_token)
        dservice = api.SERVICE.get(service_id)

        if not dservice:
            raise fault.ItemNotFoundFault("The service could not be found")

        #Delete Related Endpointtemplates and Endpoints.
        endpoint_templates = api.ENDPOINT_TEMPLATE.get_by_service(service_id)
        if endpoint_templates != None:
            for endpoint_template in endpoint_templates:
                endpoints = api.ENDPOINT_TEMPLATE.\
                    endpoint_get_by_endpoint_template(endpoint_template.id)
                if endpoints != None:
                    for endpoint in endpoints:
                        api.ENDPOINT_TEMPLATE.endpoint_delete(endpoint.id)
                api.ENDPOINT_TEMPLATE.delete(endpoint_template.id)
        #Delete Related Role and RoleRefs
        roles = api.ROLE.get_by_service(service_id)
        if roles != None:
            for role in roles:
                role_refs = api.ROLE.ref_get_by_role(role.id)
                if role_refs != None:
                    for role_ref in role_refs:
                        api.ROLE.ref_delete(role_ref.id)
                api.ROLE.delete(role.id)
        api.SERVICE.delete(service_id)

    def get_credentials(self, admin_token, user_id, marker, limit, url):
        validate_admin_token(admin_token)
        ts = []
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        ts.append(PasswordCredentials(duser.name, None))
        links = []
        return Credentials(ts, links)

    def get_password_credentials(self, admin_token, user_id):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        if not duser.password:
            raise fault.ItemNotFoundFault(
                "Password credentials could not be found")
        return PasswordCredentials(duser.name, None)

    def delete_password_credentials(self, admin_token, user_id):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")
        values = {'password': None}
        api.USER.update(user_id, values)
        return

    def update_password_credentials(self, admin_token,
        user_id, password_credentials):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        if password_credentials.user_name is None\
            or not password_credentials.user_name.strip():
            raise fault.BadRequestFault("Expecting a username.")
        duser_name = api.USER.get_by_name(password_credentials.user_name)
        if duser_name.id != duser.id:
            raise fault.UserConflictFault(
                "A user with that name already exists")
        values = {'password': password_credentials.password, \
            'name': password_credentials.user_name}
        api.USER.update(user_id, values)
        duser = api.USER.get(user_id)
        return PasswordCredentials(duser.name, duser.password)

    def create_password_credentials(self, admin_token, user_id, \
        password_credentials):
        validate_admin_token(admin_token)
        duser = api.USER.get(user_id)
        if not duser:
            raise fault.ItemNotFoundFault("The user could not be found")

        if password_credentials.user_name is None or\
            not password_credentials.user_name.strip():
            raise fault.BadRequestFault("Expecting a username.")

        if password_credentials.user_name != duser.name:
            duser_name = api.USER.get_by_name(password_credentials.user_name)
            if duser_name:
                raise fault.UserConflictFault(
                    "A user with that name already exists")
        if duser.password:
            raise fault.BadRequestFault(
                "Password credentials already available.")
        values = {'password': password_credentials.password, \
            'name': password_credentials.user_name}
        api.USER.update(user_id, values)
        duser = api.USER.get(user_id)
        return PasswordCredentials(duser.name, duser.password)

    def get_links(self, url, prev, next, limit):
        """Method to form and return pagination links."""
        links = []
        if prev:
            links.append(atom.Link('prev', "%s?marker=%s&limit=%s" \
                                                % (url, prev, limit)))
        if next:
            links.append(atom.Link('next', "%s?marker=%s&limit=%s" \
                                                % (url, next, limit)))
        return links
