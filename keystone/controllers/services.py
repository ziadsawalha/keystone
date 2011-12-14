from keystone import utils
from keystone.common import wsgi
from keystone.logic.types.service import Service
from keystone.logic import service
from . import get_marker_limit_and_url


class ServicesController(wsgi.Controller):
    """Controller for Service related operations"""

    def __init__(self, options):
        self.options = options
        self.identity_service = service.IdentityService(options)

    @utils.wrap_error
    def create_service(self, req):
        service = utils.get_normalized_request_content(Service, req)
        return utils.send_result(201, req,
            self.identity_service.create_service(utils.get_auth_token(req),
                service))

    @utils.wrap_error
    def get_services(self, req):
        service_name = req.GET["name"] if "name" in req.GET else None
        if service_name:
            tenant = self.identity_service.get_service_by_name(
                    utils.get_auth_token(req), service_name)
            return utils.send_result(200, req, tenant)
        else:
            marker, limit, url = get_marker_limit_and_url(req)
            services = self.identity_service.get_services(
                utils.get_auth_token(req), marker, limit, url)
            return utils.send_result(200, req, services)

    @utils.wrap_error
    def get_service(self, req, service_id):
        service = self.identity_service.get_service(
            utils.get_auth_token(req), service_id)
        return utils.send_result(200, req, service)

    @utils.wrap_error
    def delete_service(self, req, service_id):
        rval = self.identity_service.delete_service(utils.get_auth_token(req),
            service_id)
        return utils.send_result(204, req, rval)
