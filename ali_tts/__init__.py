import os
from random import randint
import websocket
import datetime
import hashlib
import base64
import hmac
import uuid
import json
from urllib import parse
import time
import requests
import ssl
from wsgiref.handlers import format_date_time
from datetime import datetime
from time import mktime
from appPublic.audioplayer import AudioPlayer
from appPublic.background import Background
from appPublic.http_client import Http_Client

from .version import __version__
from unitts.basedriver import BaseDriver
from unitts.voice import Voice

import tempfile
import wave

Voices = [
	Voice('aiqi','Aiqi', ['zh_CN', 'en_US'], '0', 24),
	Voice('aicheng','Aicheng', ['zh_CN', 'en_US'], '1', 24),
	Voice('aijia','Aijia', ['zh_CN', 'en_US'], '0', 24),
	Voice('siqi','sijia', ['zh_CN', 'en_US'], '0', 24),
	Voice('sijia','Sijia', ['zh_CN', 'en_US'], '0', 24),
	Voice('mashu','mashu', ['zh_CN', 'en_US'], '1', 14),
	Voice('yueer','Yueer', ['zh_CN', 'en_US'], '0', 14),
	Voice('nuoxi','Nuoxi', ['zh_CN', 'en_US'], '0', 24),
	Voice('aida','Aida', ['zh_CN', 'en_US'], '1', 24),
	Voice('sicheng','Sicheng', ['zh_CN', 'en_US'], '1', 24),
	Voice('ninger','Ninger', ['zh_CN', 'en_US'], '0', 24),
	Voice('xiaoyun','Xiaoyun', ['zh_CN', 'en_US'], '0', 24),
	Voice('xiaogang','Xiaogang', ['zh_CN', 'en_US'], '1', 24),
	Voice('ruilin','Ruilin', ['zh_CN', 'en_US'], '0', 24),
]

def wavhead(wavfile, nchannels=1, framerate=16000):
	wf = wave.open(wavfile, 'wb')
	wf.setnchannels(nchannels)
	wf.setsampwidth(2)
	wf.setframerate(framerate)
	return wf

def temp_file(suffix='.txt'):
	x = tempfile.mkstemp(suffix=suffix)
	os.close(x[0])
	return x[1]

app_info = {}

def set_app_info(appid, appkey, appsecret):
	app_info.update({
		'appid':appid,
		'appkey':appkey,
		'appsecret':appsecret
	})

def buildDriver(proxy):
	return AliTTSDriver(proxy)

class AccessToken:
	@staticmethod
	def _encode_text(text):
		encoded_text = parse.quote_plus(text)
		return encoded_text.replace('+', '%20').replace('*', '%2A').replace('%7E', '~')
	@staticmethod
	def _encode_dict(dic):
		keys = dic.keys()
		dic_sorted = [(key, dic[key]) for key in sorted(keys)]
		encoded_text = parse.urlencode(dic_sorted)
		return encoded_text.replace('+', '%20').replace('*', '%2A').replace('%7E', '~')
	@staticmethod
	def create_token(access_key_id, access_key_secret):
		parameters = {'AccessKeyId': access_key_id,
					  'Action': 'CreateToken',
					  'Format': 'JSON',
					  'RegionId': 'cn-shanghai',
					  'SignatureMethod': 'HMAC-SHA1',
					  'SignatureNonce': str(uuid.uuid1()),
					  'SignatureVersion': '1.0',
					  'Timestamp': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
					  'Version': '2019-02-28'}
		# 构造规范化的请求字符串
		query_string = AccessToken._encode_dict(parameters)
		print('规范化的请求字符串: %s' % query_string)
		# 构造待签名字符串
		string_to_sign = 'GET' + '&' + AccessToken._encode_text('/') + '&' + AccessToken._encode_text(query_string)
		print('待签名的字符串: %s' % string_to_sign)
		# 计算签名
		secreted_string = hmac.new(bytes(access_key_secret + '&', encoding='utf-8'),
								   bytes(string_to_sign, encoding='utf-8'),
								   hashlib.sha1).digest()
		signature = base64.b64encode(secreted_string)
		print('签名: %s' % signature)
		# 进行URL编码
		signature = AccessToken._encode_text(signature)
		print('URL编码后的签名: %s' % signature)
		# 调用服务
		full_url = 'http://nls-meta.cn-shanghai.aliyuncs.com/?Signature=%s&%s' % (signature, query_string)
		print('url: %s' % full_url)
		# 提交HTTP GET请求
		response = requests.get(full_url)
		if response.ok:
			root_obj = response.json()
			key = 'Token'
			if key in root_obj:
				token = root_obj[key]['Id']
				expire_time = root_obj[key]['ExpireTime']
				return token, expire_time
		print(response.text)
		return None, None

class AliTTSDriver(BaseDriver):
	def __init__(self, proxy):
		BaseDriver.__init__(self, proxy)
		self.urls = {
			'shanghai':'nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts',
			'beijing':'nls-gateway-cn-beijing.aliyuncs.com/stream/v1/tts',
			'shenzhen':'nls-gateway-cn-shenzhen.aliyuncs.com/stream/v1/tts'
		}
		self.ready = False
		self.APPID = app_info.get('appid')
		self.APIKey = app_info.get('appkey')
		self.APISecret = app_info.get('appsecret')
		self.token, self.exptime = AccessToken.create_token(self.APIKey, \
										self.APISecret)
		self.player = AudioPlayer(on_stop=self.speak_finish)
		self.params = {
			"appkey":self.APPID,
			"token":self.token,
			"format":"wav",
			"sample_rate":"16000",
			"voice":"xiaoyun",
			"volume":50,
			"speech_rate":"0",
			"pitch_rate":"0"
		}
		self.headers = {
			'Content-Type':'application/json',
		}

	def geturl(self):
		return 'https://' + self.urls.get('beijing')

	def ali_tts(self, text, params = {}):
		d = self.params.copy()
		d.update({
			'text':text
		})
		# d.update(params)
		url = self.geturl()
		resp = requests.post(url, params=d)
		ct = resp.headers.get('Content-Type')
		if not ct or ct == 'application/json':
			print('Error:', resp.text)
			return None
		bdata = resp.content
		audiofile = temp_file(suffix='.wav')
		self.wav_fd = wavhead(audiofile)
		self.wav_fd.writeframes(bdata)
		self.wav_fd.close()
		return audiofile

	def pre_command(self, sentence):
		attrs = self.normal_voice
		if sentence.dialog:
			attrs = self.dialog_voice
		x = self.ali_tts(sentence.text)
		if x is None:
			return None, None
		return sentence.start_pos, x

	def command(self, pos, audiofile):
		print('pos=', pos, 'audiofile=', audiofile)
		self.player.set_source(audiofile)
		self.player.play()

	def stop(self):
		if self._proxy.isBusy():
			self._completed = False
		self.player.stop()

	def getProperty(self, name):
		if name == 'normal_voice':
			return self.normal_voice
		if name == 'dialog_voice':
			return self.dialog_voice

		if name == 'voices':
			return Voices

		if name == 'voice':
			for v in Voices:
				if v.id == self.voice:
					return v
			return None
		if name == 'rate':
			return self.rate
		if name == 'volume':
			return self.volume
		if name == 'pitch':
			return self.pitch

	def setProperty(self, name, value):
		if name == 'normal_voice':
			self.normal_voice = value
		if name == 'dialog_voice':
			self.dialog_voice = value
		if name == 'voice':
			self.voice = value
		if name == 'rate':
			self.rate = value
		if name == 'pitch':
			self.rate = value
		if name == 'language':
			self.language = value
		if name == 'volume':
			self.volume = value
