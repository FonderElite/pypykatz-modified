#!/usr/bin/env python3
#
# Author:
#  Tamas Jos (@skelsec)
#
import io
import logging
from pypykatz.commons.common import *
from pypykatz.crypto.des import *
from pypykatz.lsadecryptor.lsa_templates import *

class LsaDecryptor():
	def __init__(self, reader, decryptor_template):
		self.reader = reader
		self.decryptor_template = decryptor_template
		self.iv = None
		self.aes_key = None
		self.des_key = None
		
		self.acquire_crypto_material()
		
	def acquire_crypto_material(self):
		logging.log(1, '[LsaDecryptor] Acquireing crypto stuff...')
		sigpos = self.find_signature()
		self.reader.move(sigpos)
		data = self.reader.peek(0x50)
		logging.log(1,'[LsaDecryptor] Memory looks like this around the signature\n%s' % hexdump(data, start = sigpos))
		self.iv = self.get_IV(sigpos)
		self.des_key = self.get_des_key(sigpos)
		self.aes_key = self.get_aes_key(sigpos)
		
	def get_des_key(self, pos):
		logging.log(1, '[LsaDecryptor] Acquireing DES key...')
		return self.get_key(pos, self.decryptor_template.key_pattern.offset_to_DES_key_ptr)
		
	def get_aes_key(self, pos):
		logging.log(1, '[LsaDecryptor] Acquireing AES key...')
		return self.get_key(pos, self.decryptor_template.key_pattern.offset_to_AES_key_ptr)
		
	def find_signature(self):
		logging.log(1, '[LsaDecryptor] Looking for main struct signature in memory...')
		fl = self.reader.find_all_global(self.decryptor_template.key_pattern.signature)
		if len(fl) == 0:
			logging.warning('[LsaDecryptor] signature not found! %s' % self.decryptor_template.key_pattern.signature.hex())
			raise Exception('LSA signature not found!')
			
		logging.log(1,'[LsaDecryptor] Found candidates on the following positions: %s' % ' '.join(hex(x) for x in fl))
		logging.log(1,'[LsaDecryptor] Selecting first one @ 0x%08x' % fl[0])
		return fl[0]

	def get_IV(self, pos):
		logging.log(1, '[LsaDecryptor] Reading IV')
		#print('Offset to IV: %s' % hex(self.decryptor_template.key_pattern.offset_to_IV_ptr))
		ptr_iv = self.reader.get_ptr_with_offset(pos + self.decryptor_template.key_pattern.offset_to_IV_ptr)
		logging.log(1, '[LsaDecryptor] IV pointer takes us to 0x%08x' % ptr_iv)
		self.reader.move(ptr_iv)
		data = self.reader.read(self.decryptor_template.key_pattern.IV_length)
		logging.log(1, '[LsaDecryptor] IV data: %s' % hexdump(data))
		return data

	def get_key(self, pos, key_offset):
		ptr_key = self.reader.get_ptr_with_offset(pos + key_offset)
		logging.log(1, '[LsaDecryptor] key handle pointer is @ 0x%08x' % ptr_key)
		ptr_key = self.reader.get_ptr(ptr_key)
		logging.log(1, '[LsaDecryptor] key handle is @ 0x%08x' % ptr_key)
		self.reader.move(ptr_key)
		data = self.reader.peek(0x50)
		logging.log(1, '[LsaDecryptor] BCRYPT_HANLE_KEY_DATA\n%s' % hexdump(data, start = ptr_key))
		kbhk = self.decryptor_template.key_handle_struct(self.reader)
		if kbhk.verify():
			ptr_key = kbhk.ptr_key.value
			self.reader.move(ptr_key)
			data = self.reader.peek(0x50)
			logging.log(1, '[LsaDecryptor] BCRYPT_KEY_DATA\n%s' % hexdump(data, start = ptr_key))
			kbk = kbhk.ptr_key.read(self.reader, self.decryptor_template.key_struct)
			logging.log(1, '[LsaDecryptor] HARD_KEY SIZE: 0x%x' % kbk.size)
			if kbk.verify():
				logging.log(1, '[LsaDecryptor] HARD_KEY data:\n%s' % hexdump(kbk.hardkey.data))
				return kbk.hardkey.data

	def decrypt(self, encrypted):
		# TODO: NT version specific, move from here in subclasses.
		cleartext = ''
		size = len(encrypted)
		if size:
			if size % 8:
				if not self.aes_key or not self.iv:
					return cleartext
				cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
			else:
				if not self.des_key or not self.iv:
					return cleartext
				#cipher = DES3.new(self.des_key, DES3.MODE_CBC, self.iv[:8])
				cipher = triple_des(self.des_key, CBC, self.iv[:8])
			cleartext = cipher.decrypt(encrypted)
		return cleartext

	def dump(self):
		t = 'Recovered LSA encryption keys\n'
		t += 'IV ({}): {}'.format(len(self.iv), self.iv.hex())
		t +='DES_KEY ({}): {}'.format(len(self.des_key), self.des_key.hex())
		t +='AES_KEY ({}): {}'.format(len(self.aes_key), self.aes_key.hex())
		return t