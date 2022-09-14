import functools
import os
import re
from time import sleep
from typing import TYPE_CHECKING, Tuple

import requests
from celery import chain, shared_task

from cowbird.handlers.handler import HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM, Handler
from cowbird.handlers.handler_factory import HandlerFactory
from cowbird.monitoring.fsmonitor import FSMonitor
from cowbird.monitoring.monitoring import Monitoring
from cowbird.request_task import RequestTask
from cowbird.utils import CONTENT_TYPE_JSON, get_logger

if TYPE_CHECKING:
    from typing import Any

    # pylint: disable=W0611,unused-import
    from cowbird.typedefs import SettingsType

HANDLER_ADMIN_USER = "admin_user"  # nosec: B105
HANDLER_ADMIN_PASSWORD = "admin_password"  # nosec: B105

LOGGER = get_logger(__name__)


def geoserver_response_handling(func):
    """
    Decorator for response and logging handling for the different Geoserver HTTP requests.

    :param func: Function executing a http request to Geoserver
    :returns: Response object
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Geoserver responses are often full HTML pages for codes 400-499, so text/content is omitted from
        # the logs. Error responses in the 500-599 range are usually concise, so their text/content were included
        # in the logs to help eventual debugging.

        # This try/except is used to catch errors caused by an unavailable Geoserver instance.
        # Since a connection error causes the requests library to raise an exception (RequestException),
        # we can't rely on a response code and need to handle this case, so it can be seen in the logs.
        # Without this, the requests auto-retries as per RequestTask class's configurations, but
        try:
            response = func(*args, **kwargs)
        except Exception as error:
            LOGGER.error(error)
            raise requests.RequestException("Connection to Geoserver failed")

        operation = func.__name__
        response_code = response.status_code
        fail_msg_intro = f"Operation [{operation}] failed"
        regex_exists = "Workspace &#39;.*&#39; already exists"
        regex_not_found = "Workspace &#39;.*&#39; not found"

        if response_code in (200, 201):
            LOGGER.info("Operation [%s] was successful.", operation)
        elif response_code == 401 and re.search(regex_exists, response.text):
            # This is done because Geoserver's reply/error code is misleading in this case and
            # returns HTML content.
            #
            # LOGGER instead of GeoserverError because workspace existing should not block subsequent steps
            LOGGER.warning("Operation [%s] failed :Geoserver workspace already exists", operation)
        elif response_code == 401:
            raise GeoserverError(f"{fail_msg_intro} because it lacks valid authentication credentials.")
        elif response_code == 403 and operation == "_remove_workspace_request":
            raise GeoserverError(f"{fail_msg_intro} : Make sure `recurse` is set to `true` to delete workspace")
        elif response_code == 404 and re.search(regex_not_found, response.text):
            raise GeoserverError(f"{fail_msg_intro}: Geoserver workspace was not found")
        elif response_code == 404 and "No such data store" in response.text:
            raise GeoserverError(f"{fail_msg_intro} :Geoserver datastore was not found")
        elif response_code == 404 and "No such feature type" in response.text:
            raise GeoserverError(f"{fail_msg_intro} :Geoserver feature type was not found")
        elif response_code == 500:
            raise GeoserverError(f"{fail_msg_intro} : {response.text}")
        else:
            raise requests.RequestException(f"{fail_msg_intro} with HTTP error code [{response_code}]")

        return response

    return wrapper


class Geoserver(Handler, FSMonitor):
    """
    Keep Geoserver internal representation in sync with the platform.
    """
    required_params = [HANDLER_URL_PARAM, HANDLER_WORKSPACE_DIR_PARAM]

    def __init__(self, settings, name, **kwargs):
        # type: (SettingsType, str, Any) -> None
        """
        Create the geoserver handler instance.

        :param settings: Cowbird settings for convenience
        :param name: Handler name
        """
        super(Geoserver, self).__init__(settings, name, **kwargs)
        self.api_url = f"{self.url}/rest"
        self.headers = {"Content-type": CONTENT_TYPE_JSON}
        self.admin_user = kwargs.get(HANDLER_ADMIN_USER, None)
        self.admin_password = kwargs.get(HANDLER_ADMIN_PASSWORD, None)
        self.auth = (self.admin_user, self.admin_password)

    #
    # Implementation of parent classes' functions
    #

    # Handler class functions
    def get_resource_id(self, resource_full_name):
        # type:(str) -> str
        raise NotImplementedError

    def user_created(self, user_name):
        self._create_datastore_dir(user_name)
        res = chain(create_workspace.si(user_name), create_datastore.si(user_name))
        res.delay()
        LOGGER.info("Start monitoring datastore of created user [%s]", user_name)
        Monitoring().register(self._shapefile_folder_dir(user_name), True, Geoserver)

    def user_deleted(self, user_name):
        remove_workspace.delay(user_name)
        LOGGER.info("Stop monitoring datastore of created user [%s]", user_name)
        Monitoring().unregister(self._shapefile_folder_dir(user_name), self)

    def permission_created(self, permission):
        raise NotImplementedError

    def permission_deleted(self, permission):
        raise NotImplementedError

    # FSMonitor class functions
    @staticmethod
    def get_instance():
        # type: () -> Geoserver
        """
        Return the Geoserver singleton instance from the class name used to retrieve the FSMonitor from the DB.
        """
        return HandlerFactory().get_handler("Geoserver")

    def on_created(self, filename):
        """
        Call when a new file is found.

        :param filename: Relative filename of a new file
        """
        if filename.endswith(".shp"):
            workspace_name, shapefile_name = self._get_shapefile_info(filename)
            LOGGER.info("Starting Geoserver publishing process for [%s]", filename)
            res = chain(validate_shapefile.si(workspace_name, shapefile_name),
                        publish_shapefile.si(workspace_name, shapefile_name))
            res.delay()

    def on_deleted(self, filename):
        """
        Call when a file is deleted.

        :param filename: Relative filename of the removed file
        """
        if filename.endswith(".shp"):
            workspace_name, shapefile_name = self._get_shapefile_info(filename)
            remove_shapefile.delay(workspace_name, shapefile_name)

    def on_modified(self, filename):
        # type: (str) -> None
        """
        Call when a file is updated.

        :param filename: Relative filename of the updated file
        """
        # Nothing need to be done in this class as Catalog already logs file modifications.
        # Still needed to implement since part of parent FSMonitor class

    #
    # Geoserver class specific functions
    #
    def create_workspace(self, name):
        # type:(Geoserver, str) -> None
        """
        Create a new Geoserver workspace.

        :param name: Workspace name
        """
        LOGGER.info("Attempting to create Geoserver workspace [%s]", name)
        self._create_workspace_request(name)

    def remove_workspace(self, name):
        # type:(Geoserver, str) -> None
        """
        Removes a workspace from geoserver. Will also remove all datastores associated with the workspace.

        :param name: Workspace name
        """
        LOGGER.info("Attempting to remove Geoserver workspace [%s]", name)
        self._remove_workspace_request(name)

    def create_datastore(self, workspace_name):
        # type:(Geoserver, str) -> None
        """
        Create a new Geoserver workspace.

        :param self: Geoserver instance
        :param workspace_name: Workspace name where the datastore must be created
        """

        datastore_name = self._get_datastore_name(workspace_name)
        LOGGER.info("Creating datastore [%s] in geoserver workspace [%s]", datastore_name, workspace_name)

        self._create_datastore_request(workspace_name=workspace_name, datastore_name=datastore_name)
        datastore_path = self._geoserver_user_datastore_dir(workspace_name)
        self._configure_datastore_request(workspace_name=workspace_name,
                                          datastore_name=datastore_name,
                                          datastore_path=datastore_path)

    def publish_shapefile(self, workspace_name, shapefile_name):
        # type:(Geoserver, str, str) -> None
        """
        Publish a shapefile in the specified workspace.

        :param workspace_name: Name of the workspace from which the shapefile will be published
        :param shapefile_name: The shapefile's name, without file extension
        """
        LOGGER.info("Shapefile [%s] is valid", shapefile_name)
        datastore_name = self._get_datastore_name(workspace_name)
        LOGGER.info("Attempting to publish shapefile [%s] to workspace:datastore [%s : %s]",
                    shapefile_name,
                    workspace_name,
                    datastore_name)
        self._publish_shapefile_request(workspace_name=workspace_name,
                                        datastore_name=datastore_name,
                                        filename=shapefile_name)

    def validate_shapefile(self, workspace_name, shapefile_name):
        """
        Validate shapefile.

        Will look for the three other files necessary for Geoserver publishing (.prj, .dbf, .shx)
        and raise a FileNotFoundError exception if one is missing.

        :param workspace_name: Name of the workspace from which the shapefile will be published
        :param shapefile_name: The shapefile's name, without file extension
        """
        # Small wait time to prevent unnecessary failure since shapefile is a multi file format
        sleep(1)
        shapefile_extensions = [".prj", ".dbf", ".shx"]
        files_to_find = [
            f"{self._shapefile_folder_dir(workspace_name)}/{shapefile_name}{ext}" for ext in shapefile_extensions
        ]
        for file in files_to_find:
            if not os.path.isfile(file):
                LOGGER.warning("Shapefile is incomplete: Missing [%s]", file)
                raise FileNotFoundError
        LOGGER.info("Shapefile [%s] is valid", shapefile_name)

    def remove_shapefile(self, workspace_name, filename):
        # type:(Geoserver, str, str) -> None
        """
        Remove a shapefile from the specified workspace.

        :param workspace_name: Name of the workspace from which the shapefile will be removed
        :param filename: The shapefile's name, without file extension
        """
        datastore_name = self._get_datastore_name(workspace_name)
        LOGGER.info("Attempting to remove shapefile [%s] from workspace:datastore [%s : %s]",
                    filename,
                    workspace_name,
                    datastore_name)
        self._remove_shapefile_request(workspace_name=workspace_name,
                                       datastore_name=datastore_name,
                                       filename=filename)

    #
    # Helper/request functions
    #
    # The following requests were built using Geoserver's REST documentation
    # https://docs.geoserver.org/master/en/user/rest/index.html
    #
    # As well as inspired by the following projects:
    # - https://github.com/gicait/geoserver-rest
    # - https://github.com/GeoNode/geoserver-restconfig
    #
    # While sometimes harder to get working, data payloads where written in json instead of xml as they are easier
    # to parse and use without external libraries.
    @staticmethod
    def _get_shapefile_info(filename):
        # type:(str) -> Tuple[str, str]
        """
        :param filename: Relative filename of a new file
        :returns: Workspace name (str) where file is located and shapefile name (str)
        """
        split_path = filename.split("/")
        workspace = split_path[-3]
        shapefile_name, _ = split_path[-1].split(".")

        return workspace, shapefile_name

    @staticmethod
    def _get_datastore_name(workspace_name):
        # type: (str) -> str
        """
        Return datastore name used to represent the datastore inside Geoserver.

        To be used in the HTTP requests sent to Geoserver.
        This name does not exist on the file system.
        """
        return f"shapefile_datastore_{workspace_name}"

    def _shapefile_folder_dir(self, workspace_name):
        # type: (str) -> str
        """
        Returns the path to the user's shapefile datastore inside the file system.
        """
        return os.path.join(self.workspace_dir, workspace_name, "shapefile_datastore")

    @staticmethod
    def _geoserver_user_datastore_dir(user_name):
        # type: (str) -> str
        """
        Returns the path to the user's shapefile datastore inside the Geoserver instance container.

        Uses the ``WORKSPACE_DIR`` env variable mapped in the Geoserver container.
        """
        return os.path.join("/user_workspaces", user_name, "shapefile_datastore")

    @geoserver_response_handling
    def _create_workspace_request(self, workspace_name):
        # type:(Geoserver, str) -> requests.Response
        """
        Request to create a new workspace.

        :param workspace_name: Name of workspace to be created
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/"
        payload = {"workspace": {"name": workspace_name, "isolated": "True"}}
        response = requests.post(url=request_url, json=payload, auth=self.auth,
                                 headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _remove_workspace_request(self, workspace_name):
        # type:(Geoserver, str) -> requests.Response
        """
        Request to remove workspace and all associated datastores and layers.

        :param workspace_name: Name of workspace to remove
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/{workspace_name}?recurse=true"
        response = requests.delete(url=request_url, auth=self.auth,
                                   headers=self.headers, timeout=self.timeout)
        return response

    def _create_datastore_dir(self, workspace_name):
        # type:(str) -> None
        datastore_folder_path = self._shapefile_folder_dir(workspace_name)
        try:
            os.mkdir(datastore_folder_path)
        except FileExistsError:
            LOGGER.info("User datastore directory already existing (skip creation): [%s]", datastore_folder_path)

    @geoserver_response_handling
    def _create_datastore_request(self, workspace_name, datastore_name):
        # type:(Geoserver, str, str) -> requests.Response
        """
        Initial creation of the datastore with no connection parameters.

        :param workspace_name: Name of the workspace in which the datastore is created
        :param datastore_name: Name of the datastore that will be created
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/{workspace_name}/datastores"
        payload = {
            "dataStore": {
                "name": datastore_name,
                "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {
                    "entry": []
                },
            }
        }
        response = requests.post(url=request_url, json=payload, auth=self.auth,
                                 headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _configure_datastore_request(self, workspace_name, datastore_name, datastore_path):
        # type:(Geoserver, str, str, str) -> requests.Response
        """
        Configures the connection parameters of the datastore.

        This is done as a secondary step because Geoserver tends to create the wrong type of datastore
        (shapefile instead of directory of shapefiles) when setting them at creation.

        :param workspace_name: Name of the workspace in which the datastore is created
        :param datastore_name: Name of the datastore that will be created
        :returns: Response object
        """
        geoserver_datastore_path = f"file://{datastore_path}"
        request_url = f"{self.api_url}/workspaces/{workspace_name}/datastores/{datastore_name}"
        payload = {
            "dataStore": {
                "name": datastore_name,
                "type": "Directory of spatial files (shapefiles)",
                "connectionParameters": {
                    "entry": [
                        {"$": "UTF-8",
                         "@key": "charset"},
                        {"$": "shapefile",
                         "@key": "filetype"},
                        {"$": "true",
                         "@key": "create spatial index"},
                        {"$": "true",
                         "@key": "memory mapped buffer"},
                        {"$": "GMT",
                         "@key": "timezone"},
                        {"$": "true",
                         "@key": "enable spatial index"},
                        {"$": f"http://{datastore_name}",
                         "@key": "namespace"},
                        {"$": "true",
                         "@key": "cache and reuse memory maps"},
                        {"$": geoserver_datastore_path,
                         "@key": "url"},
                        {"$": "shape",
                         "@key": "fstype"},
                    ]
                },
            }
        }
        response = requests.put(url=request_url, json=payload, auth=self.auth,
                                headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _publish_shapefile_request(self, workspace_name, datastore_name, filename):
        # type:(Geoserver, str, str, str) -> requests.Response
        """
        Request to publish a shapefile in Geoserver. Does so by creating a `Feature type` in Geoserver.

        :param workspace_name: Workspace where file will be published
        :param datastore_name: Datastore where file will be published
        :param filename: Name of the shapefile (with no extensions)
        :returns: Response object
        """
        request_url = f"{self.api_url}/workspaces/{workspace_name}/datastores/{datastore_name}/featuretypes"

        # This is just a basic example. There are lots of other attributes that can be configured
        # https://docs.geoserver.org/latest/en/api/#1.0.0/featuretypes.yaml
        payload = {
            "featureType": {
                "name": filename,
                "nativeCRS": """
                                GEOGCS[
                                    "WGS 84", 
                                    DATUM[
                                        "World Geodetic System 1984",
                                        SPHEROID["WGS 84", 6378137.0, 298.257223563, AUTHORITY["EPSG","7030"]],
                                        AUTHORITY["EPSG","6326"]
                                    ],
                                    PRIMEM["Greenwich", 0.0, AUTHORITY["EPSG","8901"]],
                                    UNIT["degree", 0.017453292519943295],
                                    AXIS["Geodetic longitude", EAST],
                                    AXIS["Geodetic latitude", NORTH],
                                    AUTHORITY["EPSG","4326"]
                                ]
                            """,
                "srs": "EPSG:4326",
                "projectionPolicy": "REPROJECT_TO_DECLARED",
                "maxFeatures": 5000,
                "numDecimals": 6,
            }
        }
        response = requests.post(url=request_url, json=payload, auth=self.auth,
                                 headers=self.headers, timeout=self.timeout)
        return response

    @geoserver_response_handling
    def _remove_shapefile_request(self, workspace_name, datastore_name, filename):
        # type:(Geoserver, str, str, str) -> requests.Response
        """
        Request to remove specified Geoserver `Feature type` and corresponding layer.

        :param workspace_name: Workspace where file is published
        :param datastore_name: Datastore where file is published
        :param filename: Name of the shapefile (with no extensions)
        :returns: Response object
        """
        request_url = (
            f"{self.api_url}/workspaces/{workspace_name}/datastores/{datastore_name}"
            f"/featuretypes/{filename}?recurse=true"
        )
        response = requests.delete(url=request_url, auth=self.auth,
                                   headers=self.headers, timeout=self.timeout)
        return response


@shared_task(bind=True, base=RequestTask)
def create_workspace(_task, user_name):
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return Geoserver.get_instance().create_workspace(user_name)


@shared_task(bind=True, base=RequestTask)
def create_datastore(_task, datastore_name):
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return Geoserver.get_instance().create_datastore(datastore_name)


@shared_task(bind=True, base=RequestTask)
def remove_workspace(_task, workspace_name):
    # Avoid any actual logic in celery task handler, only task related stuff should be done here
    return Geoserver.get_instance().remove_workspace(workspace_name)


@shared_task(bind=True, autoretry_for=(FileNotFoundError,), retry_backoff=True, max_retries=8)
def validate_shapefile(_task, workspace_name, shapefile_name):
    return Geoserver.get_instance().validate_shapefile(workspace_name, shapefile_name)


@shared_task(bind=True, base=RequestTask)
def publish_shapefile(_task, workspace_name, shapefile_name):
    return Geoserver.get_instance().publish_shapefile(workspace_name, shapefile_name)


@shared_task(bind=True, base=RequestTask)
def remove_shapefile(_task, workspace_name, shapefile_name):
    return Geoserver.get_instance().remove_shapefile(workspace_name, shapefile_name)


class GeoserverError(Exception):
    """
    Generic Geoserver error used to break request chains, as RequestTask only retries for a specific exception
    (RequestException).
    """