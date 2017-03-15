"""
TODO:

Example usage can be found in the example.py file
"""
import socket
from socket import AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, SO_BROADCAST

from raspyrfm_client.device.base import Device


class RaspyRFMClient:
    """
    This class is the main interface for generating and sending signals.
    """

    """
    This dictionary maps manufacturer and model constants to their implementation class.
    It is filled automatically when creating an instance of this class.
    """
    DEVICE_IMPLEMENTATIONS_DICT = {}

    _broadcast_message = b'SEARCH HCGW'

    def __init__(self, host: str = None, port: int = 49880):
        """
        Creates a new client object.

        :param host: host address of the RaspyRFM module
        :param port: the port on which the RaspyRFM module is listening
        """

        self._host = host
        self._port = port

        self._manufacturer = None
        self._model = None
        self._firmware_version = None

        RaspyRFMClient.reload_device_implementations()

    @staticmethod
    def reload_device_implementations() -> None:
        """
        Finds device implementations in the "device" package.
        This works by searching for classes that have the device base class as a superclass
        """

        global DEVICE_IMPLEMENTATIONS_DICT
        DEVICE_IMPLEMENTATIONS_DICT = {}

        print("Loading implementation classes...")

        def import_submodules(package, recursive=True):
            """ Import all submodules of a module, recursively, including subpackages

            :param package: package (name or actual module)
            :param recursive: loads all subpackages
            :type package: str | module
            :rtype: dict[str, types.ModuleType]
            """
            import pkgutil
            import importlib

            if isinstance(package, str):
                package = importlib.import_module(package)
            results = {}
            for loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
                full_name = package.__name__ + '.' + name
                results[full_name] = importlib.import_module(full_name)
                if recursive and is_pkg:
                    results.update(import_submodules(full_name))
            return results

        def get_all_subclasses(base_class):
            """
            Returns a list of all currently imported classes that are subclasses (even multiple levels)
            of the specified base class.
            :param base_class: base class to match classes to
            :return: list of classes
            """
            all_subclasses = []

            for subclass in base_class.__subclasses__():
                all_subclasses.append(subclass)
                all_subclasses.extend(get_all_subclasses(subclass))

            return all_subclasses

        from raspyrfm_client.device import manufacturer
        import_submodules(manufacturer)

        for device_implementation in get_all_subclasses(Device):
            device_instance = device_implementation()
            brand = device_instance.get_manufacturer()
            model = device_instance.get_model()

            if brand not in DEVICE_IMPLEMENTATIONS_DICT:
                DEVICE_IMPLEMENTATIONS_DICT[brand] = {}

            DEVICE_IMPLEMENTATIONS_DICT[brand][model] = device_implementation

    def search(self) -> str:
        """
        Sends a local network broadcast with a specified message.
        If a gateway is present it will respond to this broadcast.

        If a valid response is found the properties of this client object will be updated accordingly.

        :return: ip of the detected gateway
        """
        cs = socket.socket(AF_INET, SOCK_DGRAM)
        cs.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        cs.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)

        cs.sendto(self._broadcast_message, ('255.255.255.255', self._port))

        cs.setblocking(True)
        cs.settimeout(1)

        data = None
        try:
            data, address = cs.recvfrom(4096)
            print("Received message: \"%s\"" % data)
            print("Address: " + address[0])

            message = data.decode()

            # abort if response is invalid
            if not message.startswith('HCGW:'):
                print("Invalid response")
                return None

            # RaspyRFM response:
            # "HCGW:VC:Seegel Systeme;MC:RaspyRFM;FW:1.00;IP:192.168.2.124;;"

            # try to parse data if valid
            self._manufacturer = message[message.index('VC:') + 3:message.index(';MC')]
            self._model = message[message.index('MC:') + 3:message.index(';FW')]
            self._firmware_version = message[message.index('FW:') + 3:message.index(';IP')]
            parsed_host = message[message.index('IP:') + 3:message.index(';;')]

            if self._host is None:
                if parsed_host != address[0]:
                    self._host = address[0]
                else:
                    self._host = parsed_host

            return parsed_host

        except socket.timeout:
            print("Timeout")
            print("Data: " + str(data))
            return None

    def get_manufacturer(self) -> str:
        """
        :return: the manufacturer description
        """
        return self._manufacturer

    def get_model(self) -> str:
        """
        :return: the model description
        """
        return self._model

    def get_host(self) -> str:
        """
        :return: the ip/host address of the gateway (if one was found or specified manually)
        """
        return self._host

    def get_port(self) -> int:
        """
        :return: the port of the gateway
        """
        return self._port

    def get_firmware_version(self) -> str:
        """
        :return: the gateway firmware version
        """
        return self._firmware_version

    @staticmethod
    def get_device(manufacturer: str, model: str) -> Device:
        return DEVICE_IMPLEMENTATIONS_DICT[manufacturer][model]()

    @staticmethod
    def list_supported_devices():
        for manufacturer in DEVICE_IMPLEMENTATIONS_DICT:
            print(manufacturer)
            for model in DEVICE_IMPLEMENTATIONS_DICT[manufacturer].keys():
                print("  " + model)

                # import pprint
                # pprint.pprint(DEVICE_IMPLEMENTATIONS_DICT)

    def send(self, device: Device, action: str) -> None:
        """
        Use this method to generate codes for actions on supported devices.
        It will generates a string that can be interpreted by the the RaspyRFM module.
        The string contains information about the rc signal that should be sent.

        :param device: the device
        :param action: action to execute
        """

        if self._host is None:
            print("Missing host, nothing sent.")
            return

        message = device.generate_code(action)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
        sock.sendto(bytes(message, "utf-8"), (self._host, self._port))
