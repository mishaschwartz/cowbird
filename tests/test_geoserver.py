# pylint: disable=protected-access
import os

import pytest
import yaml

from cowbird.constants import COWBIRD_ROOT
from cowbird.services.impl.geoserver import Geoserver


def get_geoserver_settings():
    """
    Setup basic parameters for an unmodified local test run (using the example files)
    unless environment variables are set.
    """
    config_path = os.path.join(COWBIRD_ROOT, "config/config.example.yml")
    settings_dictionary = yaml.safe_load(open(config_path, "r"))
    geoserver_settings = settings_dictionary["services"]["Geoserver"]
    if "${HOSTNAME}" in geoserver_settings["url"]:
        hostname = os.getenv("HOSTNAME", "localhost")
        geoserver_settings["url"] = geoserver_settings["url"].replace("${HOSTNAME}", hostname)
    if "${WORKSPACE_DIR}" in geoserver_settings["workspace_dir"]:
        workdir = os.getenv("WORKSPACE_DIR", "/tmp/test-datastore")
        geoserver_settings["workspace_dir"] = geoserver_settings["workspace_dir"].replace("${WORKDIR}", workdir)
    geoserver_settings["ssl_verify"] = os.getenv("COWBIRD_SSL_VERIFY", False)
    return geoserver_settings


GEOSERVER_SETTINGS = get_geoserver_settings()


@pytest.mark.geoserver
class TestGeoserverRequests:
    workspaces = {
        "creation": "test-workspace-creation",
        "creation-duplicate": "test-duplicate-workspace",
        "empty-remove": "test-empty-workspace-removal",
        "remove": "test-workspace-removal",
        "datastore-create": "test-datastore-creation",
        "datastore-config": "test-datastore-configuration",
        "datastore-duplicate": "test-duplicate-datastore"
    }

    @pytest.fixture
    def geoserver(self):
        # Bypasses ServiceFactory() to prevent side effects in other tests.
        geoserver = Geoserver(settings={}, name="Geoserver", **GEOSERVER_SETTINGS)
        geoserver.ssl_verify = GEOSERVER_SETTINGS["ssl_verify"]
        return geoserver

    def teardown_class(self):
        # Couldn't pass fixture to teardown function.
        teardown_gs = Geoserver(settings={}, name="Geoserver", **GEOSERVER_SETTINGS)
        teardown_gs.ssl_verify = GEOSERVER_SETTINGS["ssl_verify"]
        for _, workspace in self.workspaces.items():
            teardown_gs._remove_workspace_request(workspace_name=workspace)

    def test_workspace_creation(self, geoserver):
        request = geoserver._create_workspace_request(workspace_name=self.workspaces["creation"])
        assert request.status_code == 201

    def test_empty_workspace_removal(self, geoserver):
        geoserver._create_workspace_request(self.workspaces["empty-remove"])
        request = geoserver._remove_workspace_request(workspace_name=self.workspaces["empty-remove"])
        assert request.status_code == 200

    def test_duplicate_workspace(self, geoserver):
        request = geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert request.status_code == 201
        request = geoserver._create_workspace_request(workspace_name=self.workspaces["creation-duplicate"])
        assert request.status_code == 401

    def test_workspace_removal(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["remove"])
        geoserver._create_datastore_request(workspace_name=self.workspaces["remove"],
                                            datastore_name="test-datastore")
        request = geoserver._remove_workspace_request(workspace_name=self.workspaces["remove"])
        assert request.status_code == 200

    def test_datastore_creation(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-create"])
        request = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-create"],
                                                      datastore_name="test-datastore")
        assert request.status_code == 201

    def test_datastore_creation_missing_workspace(self, geoserver):
        request = geoserver._create_datastore_request(workspace_name="test-nonexistent-workspace",
                                                      datastore_name="test-datastore")
        assert request.status_code == 500

    def test_datastore_configuration(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-config"])
        geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-config"],
                                            datastore_name="test-datastore")

        request = geoserver._configure_datastore_request(workspace_name=self.workspaces["datastore-config"],
                                                         datastore_name="test-datastore",
                                                         datastore_path=geoserver.workspace_dir)
        assert request.status_code == 200

    def test_duplicate_datastore(self, geoserver):
        geoserver._create_workspace_request(workspace_name=self.workspaces["datastore-duplicate"])
        request = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-duplicate"],
                                                      datastore_name="test-datastore")
        assert request.status_code == 201

        request = geoserver._create_datastore_request(workspace_name=self.workspaces["datastore-duplicate"],
                                                      datastore_name="test-datastore")
        assert request.status_code == 500
