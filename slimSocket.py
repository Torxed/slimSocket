from socket import *
from select import epoll, EPOLLIN, EPOLLOUT, EPOLLHUP
class slimIdentity():
	def __init__(self, parent, socket, address=None, parsers={}):
		self.parent = parent
		self.socket = socket
		self.address = address
		self.parsers = parsers

		self.info = {'addr' : address, 'fileno' : None}

		self.data = b''

		self.keep_alive = True
		self.parent = parent
		self.id = self.info['addr'][0]

	def __repr__(self):
		return 'client[{}:{}]'.format(*self.info['addr'])

	def recv(self, buffert=8192):
		if self.parent.poll(fileno=self.socket.fileno()):
			try:
				d = self.socket.recv(buffert)
			except ConnectionResetError:
				d = ''
			if len(d) == 0:
				self.close()
				return None
			self.data += d
			return len(self.data)
		return None

	# def id(self):
	# 	return self.info['addr'][0] 

	def close(self):
		self.socket.close()
		return True

	def send(self, d):
		self.respond(d)

	def respond(self, d):
		if d is None: d = b'HTTP/1.1 200 OK\r\n\r\n'

		if type(d) == dict: d = json.dumps(d)
		if type(d) != bytes: d = bytes(d, 'UTF-8')

		#print('>', d)
		self.socket.send(d)
		return True

	def parse(self):
		data = self.data.decode('UTF-8')
		try:
			data = json.loads(data)
		except Exception as e:
			pass
		for parser in self.parsers:
			for response in self.parsers[parser].parse(self, data, {}, self.socket.fileno(), self.address):
				return response

class socket_serve():
	def __init__(self, parsers={}, address='', port=1337):
		self.sock = socket()
		self.sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
		self.sock.bind((address, port))
		self.ssl = False

		self.pollobj = epoll()
		self.sockets = {}
		self.parsers = parsers

		while drop_privileges() is None:
			log('Waiting for privileges to drop.', once=True, level=5, origin='slimSocket', function='init')

		self.sock.listen(10)
		self.main_so_id = self.sock.fileno()
		self.pollobj.register(self.sock.fileno(), EPOLLIN)

	def accept(self, client_wrapper=slimIdentity):
		if self.poll(0.001, fileno=self.main_so_id):
			ns, na = self.sock.accept()
			if self.ssl:
				try:
					ns.do_handshake()
				except ssl.SSLError as e:
					## It's a notice, not a error. Started in Python3.7.2 - Not sure why.
					if e.errno == 1 and 'SSLV3_ALERT_CERTIFICATE_UNKNOWN' in e.args[1]:
						pass
			log('Accepting new client: {addr}'.format(**{'addr' : na[0]}), level=4, origin='slimSocket', function='accept')
			ns_fileno = ns.fileno()
			if ns_fileno in self.sockets:
				self.sockets[ns_fileno].close()
				del self.sockets[ns_fileno]

			self.sockets[ns_fileno] = client_wrapper(self, ns, na, self.parsers)
			self.pollobj.register(ns_fileno, EPOLLIN)
			return self.sockets[ns_fileno]
		return None

	def poll(self, timeout=0.001, fileno=None):
		d = dict(self.pollobj.poll(timeout))
		if fileno: return d[fileno] if fileno in d else None
		return d

	def close(self, fileno=None):
		if fileno:
			try:
				log(f'closing fileno: {fileno}', level=5, origin='slimSocket', function='close')
				self.pollobj.unregister(fileno)
			except FileNotFoundError:
				pass # Already unregistered most likely.
			if fileno in self.sockets:
				self.sockets[fileno].close()
			return True
		else:
			for fileno in self.sockets:
				try:
					log(f'closing fileno: {fileno}', level=5, origin='slimSocket', function='close')
					self.pollobj.unregister(fileno)
					self.sockets[fileno].socket.close()
				except:
					pass
			self.pollobj.unregister(self.main_so_id)
			self.sock.close()
