import threading
import socket
import select


def consume_socket_content(sock, timeout=0.5):
    chunks = 65536
    content = b''
    more_to_read = select.select([sock], [], [], timeout)[0]

    while more_to_read:
        new_content = sock.recv(chunks)

        if not new_content:
            break

        content += new_content
        # stop reading if no new data is received for a while
        more_to_read = select.select([sock], [], [], timeout)[0]

    return content


class Server(threading.Thread):
    """Dummy server using for unit testing"""
    WAIT_EVENT_TIMEOUT = 5

    def __init__(self, handler, host='localhost', port=0, requests_to_handle=1, wait_to_close_event=None):
        super(Server, self).__init__()

        self.handler = handler
        self.handler_results = []

        self.host = host
        self.port = port
        self.requests_to_handle = requests_to_handle

        self.wait_to_close_event = wait_to_close_event
        self.ready_event = threading.Event()
        self.stop_event = threading.Event()

    @classmethod
    def text_response_server(cls, text, request_timeout=0.5, **kwargs):
        def text_response_handler(sock):
            request_content = consume_socket_content(sock, timeout=request_timeout)
            sock.send(text.encode('utf-8'))

            return request_content


        return Server(text_response_handler, **kwargs)

    @classmethod
    def basic_response_server(cls, **kwargs):
        return cls.text_response_server(
            "HTTP/1.1 200 OK\r\n" +
            "Content-Length: 0\r\n\r\n",
            **kwargs
        )

    def run(self):
        try:
            sock = self._create_socket_and_bind()
            # in case self.port = 0
            self.port = sock.getsockname()[1]
            self.ready_event.set()
            self._handle_requests(sock)

            if self.wait_to_close_event:
                self.wait_to_close_event.wait(self.WAIT_EVENT_TIMEOUT)
        finally:
            self.ready_event.set() # just in case of exception
            sock.close()
            self.stop_event.set()

    def _create_socket_and_bind(self):
        sock = socket.socket()
        sock.bind((self.host, self.port))
        sock.listen(0)
        return sock

    def _handle_requests(self, server_sock):
        for _ in range(self.requests_to_handle):
            sock = server_sock.accept()[0]
            handler_result = self.handler(sock)

            self.handler_results.append(handler_result)

    def __enter__(self):
        self.start()
        self.ready_event.wait(self.WAIT_EVENT_TIMEOUT)
        return self.host, self.port

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.stop_event.wait(self.WAIT_EVENT_TIMEOUT)
        else:
            if self.wait_to_close_event:
                # avoid server from waiting for event timeouts
                # if an exception is found in the main thread
                self.wait_to_close_event.set()
        return False # allow exceptions to propagate