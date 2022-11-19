from napari_plugin_engine import napari_hook_implementation
from qtpy.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QListWidget, QListWidgetItem, QLabel, QFileDialog
from qtpy.QtWidgets import QSpacerItem, QSizePolicy, QInputDialog
from qtpy.QtCore import QEvent, Qt
from qtpy.QtCore import Signal, QObject, QEvent

from magicgui.widgets import FileEdit
from magicgui.types import FileDialogMode

from os import listdir
from os.path import isfile, join
import fnmatch
from napari_tools_menu import register_dock_widget
import warnings

class MyQLineEdit(QLineEdit):
    keyup = Signal()
    keydown = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            self.keyup.emit()
            return
        elif event.key() == Qt.Key_Down:
            self.keydown.emit()
            return
        super().keyPressEvent(event)

@register_dock_widget(menu="Utilities > Browse owncloud / nextcloud storage")
class OwncloudBrowser(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self._viewer = napari_viewer

        self.setLayout(QVBoxLayout())
        self._client = None

        # --------------------------------------------
        # Login / Logout
        self._server = QLineEdit()
        self._server.setText("https://")
        self._username = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)

        self._login_widget = QWidget()
        self._login_widget.setLayout(QVBoxLayout())
        self._login_widget.layout().addWidget(QLabel("Server:"))
        self._login_widget.layout().addWidget(self._server)
        self._login_widget.layout().addWidget(QLabel("Username:"))
        self._login_widget.layout().addWidget(self._username)
        self._login_widget.layout().addWidget(QLabel("Password:"))
        self._login_widget.layout().addWidget(self._password)
        verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self._login_widget.layout().addItem(verticalSpacer)

        self._login_logout = QPushButton("Logout")
        self._login_logout.clicked.connect(self._login_logout_clicked)

        # --------------------------------------------
        #  File filter
        self._current_dir = QLabel("/")
        self._folder_up = QPushButton("Up one folder")
        self._folder_up.clicked.connect(self._folder_up_clicked)
        self._search_field = MyQLineEdit("")
        self._results = QListWidget()

        # navigation in the list
        def key_up():
            if self._results.currentRow() > 0:
                self._results.setCurrentRow(self._results.currentRow() - 1)

        def key_down():
            if self._results.currentRow() < self._results.count() - 1:
                self._results.setCurrentRow(self._results.currentRow() + 1)

        self._search_field.keyup.connect(key_up)
        self._search_field.keydown.connect(key_down)
        self._search_field.textChanged.connect(self._text_changed)
        self._search_field.setPlaceholderText("Filter files by name")
        self._search_field.returnPressed.connect(self._item_double_clicked)

        #self._results.itemDoubleClicked.connect(item_double_clicked)
        self._results.itemActivated.connect(self._item_double_clicked)

        # ---------------------------------------------
        # Save button
        self._save_current_layer = QPushButton("Save / upload current layer")
        self._save_current_layer.clicked.connect(self._save_current_layer_clicked)

        self.setLayout(QVBoxLayout())

        self._search_widget = QWidget()
        self._search_widget.setLayout(QVBoxLayout())
        self._search_widget.layout().addWidget(self._current_dir)
        self._search_widget.layout().addWidget(self._folder_up)
        self._search_widget.layout().addWidget(self._search_field)

        self.layout().addWidget(self._login_widget)
        self.layout().addWidget(self._login_logout)

        self.layout().addWidget(self._search_widget)
        self.layout().addWidget(self._results)
        self.layout().addWidget(self._save_current_layer)

        # set up temporary directory
        import tempfile
        self._temp_folder = tempfile.TemporaryDirectory(prefix="napari-owncloud")

        # init GUI
        self._login_logout_clicked()

    def _login_logout_clicked(self):
        if self._login_logout.text() == "Login":
            try:
                import owncloud
            except:
                import nextcloud_client as owncloud

            # potentially disconnect first
            if self._client is not None:
                try:
                    self._client.logout()
                except:
                    pass

            # connect
            try:
                self._client = owncloud.Client(self._server.text())
                self._client.login(self._username.text(), self._password.text())
            except:
                warnings.warn("Login failed")
                self._client = None

            # remove the password after logging in or failing to
            self._password.setText("")

            if self._client is None:
                return

            self._current_dir.setText("/")
            self._directory_changed()

            self._login_logout.setText("Logout")
        else: #Logout
            if self._client is not None:
                try:
                    self._client.logout()
                except:
                    pass

            self._client = None
            self._login_logout.setText("Login")

        login = self._login_logout.text() == "Login"
        self._login_widget.setVisible(login)

        self._search_widget.setVisible(not login)
        self._results.setVisible(not login)
        self._save_current_layer.setVisible(not login)

    def _folder_up_clicked(self):
        current_dir = self._current_dir.text()
        current_path = current_dir.split("/")
        parent_path = current_path[:-2]
        self._current_dir.setText(("/").join(parent_path) + "/")

        self._directory_changed()

    def _directory_changed(self, *args, **kwargs):
        if self._client is None:
            print("Not logged in")
            return

        # str(filename_edit.value.absolute()).replace("\\", "/").replace("//", "/")
        # self.all_files = [f for f in listdir(self.current_directory) if isfile(join(self.current_directory, f))]
        self._all_files = [f.path for f in self._client.list(self._current_dir.text())]

        self._text_changed()  # update shown list
        self._folder_up.setEnabled(len(self._current_dir.text()) > 1)

    # update search
    def _text_changed(self, *args, **kwargs):
        search_string = self._search_field.text()
        if len(search_string) == 0:
            search_string = "*"

        self._results.clear()
        for path in self._all_files:
            path_elements = path.split("/")
            if len(path_elements[-1]) == 0:  # path is a directory
                file_name = path_elements[-2] + "/"
            else:  # path is a file
                file_name = path_elements[-1]

            if fnmatch.fnmatch(file_name, search_string):
                self._add_result(file_name)
        self._results.sortItems()

    def _add_result(self, file_name):
        item = QListWidgetItem(file_name)
        item.file_name = file_name
        self._results.addItem(item)

    # open file on ENTER and double click
    def _item_double_clicked(self):
        item = self._results.currentItem()
        print("Opening File", self._current_dir.text(), item.file_name)
        if item.file_name.endswith("/"): # open folder
            self._current_dir.setText(self._current_dir.text() + item.file_name)

            # create the folder locally if it doesn't exist
            import os
            temp_dir = self._temp_folder.name.replace("\\", "/") + self._current_dir.text()
            if not os.path.isdir(temp_dir):
                os.mkdir(temp_dir)

            self._directory_changed()
        else: # open file
            temp_dir = self._temp_folder.name.replace("\\", "/") + self._current_dir.text()
            # download file

            print("Downloading to ", temp_dir + item.file_name)
            self._client.get_file(
                remote_path=self._current_dir.text() + item.file_name,
                local_file=temp_dir + item.file_name
            )
            # open it
            self._viewer.open(temp_dir + item.file_name)

    def _save_current_layer_clicked(self):
        if self._client is None:
            print("Not connected")
            return
        filename, ok = QInputDialog.getText(self, "Save current layer to owncloud", "Filename")
        if not ok or filename is None or len(filename) == 0:
            return
        if not "." in filename:
            filename = filename + ".tif"

        temp_directory = self._temp_folder.name.replace("\\", "/") + self._current_dir.text()
        filenames = self._viewer.layers.save(temp_directory + filename, selected=True)
        for saved_filename in filenames:
            local_filename = saved_filename.replace("\\", "/")
            remote_filename = local_filename.replace(temp_directory, self._current_dir.text())
            print("Uploading file from", local_filename)
            print("to", remote_filename)

            self._client.put_file(remote_filename, local_filename)

        self._directory_changed()


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    return [OwncloudBrowser]
