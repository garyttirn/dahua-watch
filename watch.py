#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Version 2.1.2020
# Dahua/Amcrest Event Watcher based on https://github.com/johnnyletrois/dahua-watch
import logging
import socket
import pycurl
import time
import shlex
import subprocess

ALARM_DELAY = 30
URL_TEMPLATE = "http://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&codes=%5B{events}%5D"

CAMERAS = [
	{
		"host": "<camera IP address or hostname>",
		"port": 80,
		"user": "<camera username>",
		"pass": "<camera password>",
		"events": "VideoMotion,AudioMutation,AudioAnomaly",
		"veradevice" : "<vera camera motion sensor device id to report events>",
		"vera" : "<Vera IP address or hostname>"
	},
	{
		"host": "<camera IP address or hostname>",
		"port": 80,
		"user": "<camera IP address or hostname>",
		"pass": "<camera password>",
		"events": "VideoMotion,AudioMutation,AudioAnomaly,CrossLineDetection,FaceDetection",
		"veradevice" : "<vera camera motion sensor device id to report events>",
		"vera" : "<Vera IP address or hostname>"
	}
]

class DahuaCamera():
	def __init__(self, master, index, camera):
		self.Master = master
		self.Index = index
		self.Camera = camera
		self.CurlObj = None
		self.Connected = None
		self.Reconnect = None

		self.Alarm = dict({
			"Active": None,
			"Last": None
		})

	def OnAlarm(self, State):
		c = pycurl.Curl()
		# DEBUG c.setopt(c.VERBOSE, True)

		if State:
			c.setopt(c.URL,"http://%s:3480/data_request?id=variableset&DeviceNum=%s&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=Tripped&Value=1" % (self.Camera["vera"], self.Camera["veradevice"]))
			print("[{0}-{1}] Motion Detected)".format(self.Index, self.Camera["host"]))
		else:
			c.setopt(c.URL,"http://%s:3480/data_request?id=variableset&DeviceNum=%s&serviceId=urn:micasaverde-com:serviceId:SecuritySensor1&Variable=Tripped&Value=0" % (self.Camera["vera"], self.Camera["veradevice"]))
			print("[{0}-{1}] Motion Stopped)".format(self.Index, self.Camera["host"]))

		try:
			c.perform()
		except pycurl.error:
			print("Vera Connection error")	

		c.close()

	def OnConnect(self):
		print("[{0}-{1}] OnConnect()".format(self.Index,self.Camera["host"]))
		self.Connected = True

	def OnDisconnect(self, reason):
		# print("[{0}-{1}] OnDisconnect({2})".format(self.Index,self.Camera["host"],reason))
		self.Connected = False

	def OnTimer(self):
		if self.Alarm["Active"] == False and time.time() - self.Alarm["Last"] > ALARM_DELAY:
			self.Alarm["Active"] = None
			self.Alarm["Last"] = None

			self.OnAlarm(False)

	def OnReceive(self, data):
		Data = data.decode("utf-8", errors="ignore")
		#print("[{0}]: {1}".format(self.Index, Data))

		for Line in Data.split("\r\n"):
			if Line == "HTTP/1.1 200 OK":
				self.OnConnect()

			if not Line.startswith("Code="):
				continue

			Alarm = dict()
			for KeyValue in Line.split(';'):
				Key, Value = KeyValue.split('=')
				Alarm[Key] = Value

			self.ParseAlarm(Alarm)

	def ParseAlarm(self, Alarm):
		print("[{0}-{1}] ParseAlarm({2})".format(self.Index, self.Camera["host"], Alarm))

		if Alarm["Code"] not in self.Camera["events"].split(','):
			return

		if Alarm["action"] == "Start":
			if self.Alarm["Active"] == None:
				self.OnAlarm(True)
			self.Alarm["Active"] = True
		elif Alarm["action"] == "Stop":
			self.Alarm["Active"] = False
			self.Alarm["Last"] = time.time()


class DahuaMaster():
	def __init__(self):
		self.Cameras = []
		self.NumActivePlayers = 0

		self.CurlMultiObj = pycurl.CurlMulti()
		self.NumCurlObjs = 0

		for Index, Camera in enumerate(CAMERAS):
			DahuaCam = DahuaCamera(self, Index, Camera)
			self.Cameras.append(DahuaCam)
			Url = URL_TEMPLATE.format(**Camera)

			CurlObj = pycurl.Curl()
			DahuaCam.CurlObj = CurlObj

			CurlObj.setopt(pycurl.URL, Url)
			CurlObj.setopt(pycurl.CONNECTTIMEOUT, 30)
			CurlObj.setopt(pycurl.TCP_KEEPALIVE, 1)
			CurlObj.setopt(pycurl.TCP_KEEPIDLE, 30)
			CurlObj.setopt(pycurl.TCP_KEEPINTVL, 15)
			CurlObj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
			CurlObj.setopt(pycurl.USERPWD, "%s:%s" % (Camera["user"], Camera["pass"]))
			CurlObj.setopt(pycurl.WRITEFUNCTION, DahuaCam.OnReceive)

			self.CurlMultiObj.add_handle(CurlObj)
			self.NumCurlObjs += 1

	def OnTimer(self):
		for Camera in self.Cameras:
			Camera.OnTimer()

	def Run(self, timeout = 1.0):
		while 1:
			Ret, NumHandles = self.CurlMultiObj.perform()
			if Ret != pycurl.E_CALL_MULTI_PERFORM:
				break

		while 1:
			time.sleep(.05)
			Ret = self.CurlMultiObj.select(timeout)
			if Ret == -1:
				self.OnTimer()
				continue

			while 1:
				Ret, NumHandles = self.CurlMultiObj.perform()

				if NumHandles != self.NumCurlObjs:
					_, Success, Error = self.CurlMultiObj.info_read()

					for CurlObj in Success:
						Camera = next(filter(lambda x: x.CurlObj == CurlObj, self.Cameras))
						if Camera.Reconnect:
							continue

						Camera.OnDisconnect("Success")
						Camera.Reconnect = time.time() + 5

					for CurlObj, ErrorNo, ErrorStr in Error:
						Camera = next(filter(lambda x: x.CurlObj == CurlObj, self.Cameras))
						if Camera.Reconnect:
							continue

						Camera.OnDisconnect("{0} ({1})".format(ErrorStr, ErrorNo))
						Camera.Reconnect = time.time() + 5

					for Camera in self.Cameras:
						if Camera.Reconnect and Camera.Reconnect < time.time():
							self.CurlMultiObj.remove_handle(Camera.CurlObj)
							self.CurlMultiObj.add_handle(Camera.CurlObj)
							Camera.Reconnect = None

				if Ret != pycurl.E_CALL_MULTI_PERFORM:
					break

			self.OnTimer()

if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG)

	Master = DahuaMaster()
	Master.Run()

