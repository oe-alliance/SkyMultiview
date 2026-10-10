########################################################################################################
# Sky Multiview by Mr.Servo @OpenATV (c) 2025 - skinned by stein17 @OpenATV                            #
# Special thanks to stein17 @OpenA.TV for graphic design, skins, and icons                             #
# Special thanks to jbleyel @OpenATV for his valuable support in E2-questions                          #
# Special thanks to Anskar @OpenA.TV for consulting and testing                                        #
# -----------------------------------------------------------------------------------------------------#
# This plugin is licensed under the GNU version 3.0 <https://www.gnu.org/licenses/gpl-3.0.en.html>.    #
# This plugin is NOT free software. It is open source, you are allowed to modify it (if you keep       #
# the license), but it may not be commercially distributed. Advertise with this plugin is not allowed. #
# For other uses, permission from the authors is necessary.                                            #
########################################################################################################

from datetime import datetime
from json import load
from os.path import join, exists
from re import search
from twisted.internet.reactor import callInThread

from enigma import eTimer, eServiceReference, eEPGCache, iPlayableService, getDesktop
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Renderer.Picon import getPiconName
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Plugins.Plugin import PluginDescriptor
from Screens.AudioSelection import AudioSelection
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Tools.LoadPixmap import LoadPixmap

from . import __version__


class MVglobals:
	RELEASE = f"v{__version__}"
	MODULE_NAME = __name__.split(".")[-2]
	PLUGINPATH = resolveFilename(SCOPE_PLUGINS, "Extensions/SkyMultiview/")  # e.g. /usr/lib/enigma2/python/Plugins/Extensions/SkyMultiview/
	RESOLUTION = "FHD" if getDesktop(0).size().width() > 1300 else "HD"


mvglobals = MVglobals


class MVhelpers:
	def getEPGmvDicts(self):
		def epgSearch(queryStr):
			criteria = ("IBDTSENRW", 128, eEPGCache.PARTIAL_TITLE_SEARCH, queryStr, 1)  # SEARCH_FIELDS, MAX_RESULTS, ..., 1=CASE_INSENSITIVE_QUERY
			return self._instance.search(criteria) or []

		def getMvType(searchTitle):
			elements = searchTitle.split(",")
			dataStr = elements[0].split(":") if len(elements) > 0 else ""
			return dataStr[0].strip("'") if len(dataStr) > 0 else ""  # e.g. 'Live2.BL' or 'Live2.BLAlleSpiele,alleTore'

		def isMVchannel(sName):
			return any(txt in sName for txt in ["bundesliga", "buli", "sport"]) and search(r'\d+', sName)

		def createMultiview(mvId, sResult):
			multiviewDict = {}
			multiviewDict["mvId"] = mvId  # e.g. 'LiveBL' or 'Live2.BL'
			multiviewDict["mvSname"] = sResult[6]  # e.g. 'Live2.BL:Multiview,11.Spieltag,Sonntag'
			multiviewDict["mvSref"] = sResult[7]  # e.g. 'Fußball:2.BundesligaSonntags-Konferenz,11.Spieltag'
			multiviewDict["mvTitle"] = sResult[3].strip("'")  # e.g. '11.Spieltag,Sonntag'
			multiviewDict["mvEvent"] = sResult[4]  # e.g. '11.Spieltag,Sonntag'
			multiviewDict["mvStart"] = sResult[1]
			multiviewDict["mvDurance"] = sResult[2]
			return multiviewDict

		def createChannels(sResult):
			channelDict = {}
			channelDict["epgSname"] = sResult[6]
			channelDict["epgSref"] = sResult[7]
			channelDict["epgTitle"] = sResult[3]  # e.g. 'LiveBL:1.FSVMainz05-WerderBremen,9.Spieltag'
			channelDict["epgEvent"] = sResult[4]  # e.g. 'Fußball:Bundesliga1.FSVMainz05-WerderBremen,9.Spieltag'
			channelDict["epgStart"] = sResult[1]
			channelDict["epgDurance"] = sResult[2]
			return channelDict

		fakeEPG = join(mvglobals.PLUGINPATH, "fakeEPG.json")
		if exists(fakeEPG):  # in order to get EPG-infos during commercial breaks, for testing purposes only
			with open(fakeEPG) as file:
				mvDicts = load(file)
			return mvDicts
		mvDicts, foundEvents = [], []
		for sResult in epgSearch(": multiview"):  # OUTER LOOP: find all valid 'multiview overviews', not 'multiview hints'
			mvId, sNameLow = getMvType(sResult[3]), sResult[6].lower()
			if not mvId or "sky" not in sNameLow or not isMVchannel(sNameLow):  # skip on non-multiview overwies or non-sky-sport channels
				continue
			mvDict = createMultiview(mvId, sResult)
			mvId, mvStart = mvDict.get("mvId", 0), mvDict.get("mvStart", 0)
			for channelFound in epgSearch(f"{mvId}:"):  # INNER LOOP: find the individual broadcasts associated with the 'mvId'
				start, title, sNameLow = channelFound[1], channelFound[3], channelFound[6].lower()
				if "sky" not in sNameLow:
					continue  # skip non-sky channels
				if start >= mvStart and start - mvStart <= 1800 and len(title.split(":")) < 3:
					if f"{mvId}:" in title and "multiview" not in title.lower() and (title, start) not in foundEvents:
						foundEvents.append((title, start))
						channelDict = createChannels(channelFound)
						key = "conferences" if "konferenz" in title.lower() else "channels"
						mvDict.setdefault(key, []).append(channelDict)  # add even when list if missing
			mvDicts.append(mvDict)
		mvDicts.sort(key=lambda k: k["mvStart"])  # sort list of dicts relating start time
		newDicts = []
		for mvDict in mvDicts:
			channels = mvDict.get("channels", [])
			channels.sort(key=lambda k: k["epgSname"])  # sort list of dicts relating service name
			mvDict.update(channels=channels)
			newDicts.append(mvDict)
		return newDicts


class MVmain(Screen, MVhelpers):
	skin = """
	<screen name="MVmain" position="0,0" size="1280,720" resolution="1280,720" flags="wfNoBorder" title="Sky Multiview" backgroundColor="#FF000000">
		<widget source="audiotext" render="Label" position="0,0" size="600,30" valign="top" halign="center" font="Regular;24" textBorderColor="#00505050" textBorderWidth="1" foregroundColor="#00ffff00" backgroundColor="#16000000" transparent="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget name="mvcursor" position="0,0" size="934,628" />
		<widget source="mvtext" render="Label" position="40,690" size="150,30" font="Regular;20" valign="center" backgroundColor="#FF000000" />
		<widget source="mvtext" render="Pixmap" pixmap="~button.png" position="10,692" size="24,24" scale="1" alphatest="blend" conditional="mvtext">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_red" render="Pixmap" pixmap="~key_red.png" alphatest="blend" position="220,692" size="24,24" backgroundColor="#007a6213" objectTypes="key_red,StaticText" transparent="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_red" render="Label" position="250,690" size="180,30" noWrap="1" zPosition="+1" valign="center" font="Regular;20" halign="left" foregroundColor="grey" backgroundColor="#16000000" objectTypes="key_red,StaticText" transparent="1" />
		<widget source="key_green" render="Pixmap" pixmap="~key_green.png" alphatest="blend" position="470,692" size="24,24" backgroundColor="#00006600,#0024a424,vertical" cornerRadius="12" objectTypes="key_green,StaticText" transparent="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_green" render="Label" position="500,690" size="180,30" noWrap="1" zPosition="+1" valign="center" font="Regular;20" halign="left" foregroundColor="grey" backgroundColor="#16000000" objectTypes="key_green,StaticText" transparent="1" />
		<widget source="key_yellow" render="Pixmap" pixmap="~key_yellow.png" alphatest="blend" position="720,692" size="24,24" backgroundColor="#007a6213,#00e6c619,vertical" cornerRadius="12" objectTypes="key_yellow,StaticText" transparent="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_yellow" render="Label" position="750,690" size="180,30" noWrap="1" zPosition="+1" valign="center" font="Regular;20" halign="left" foregroundColor="grey" backgroundColor="#16000000" objectTypes="key_yellow,StaticText" transparent="1" />
		<widget source="exittext" render="Label" position="center,center" size="1280,30" valign="center" halign="center" zPosition="1" font="Regular;20" transparent="1" foregroundColor="#00FFFFFF" />
	</screen>
	"""

	def __init__(self, session, mvTupleId, mvDicts, mvinfobox):
		self.mvTupleId = mvTupleId  # =(mvId, mvSref, mvStart)
		self.mvDicts = mvDicts
		self.mvInfobox = mvinfobox
		self._instance = eEPGCache.getInstance()
		self.skin = self.skin.replace("~", f"{mvglobals.PLUGINPATH}/pics/{mvglobals.RESOLUTION}/")
		Screen.__init__(self, session)
		ServiceEventTracker(screen=self, eventmap={iPlayableService.evStart: self.serviceUpdated, iPlayableService.evUpdatedInfo: self.serviceUpdated})
		self.multiviewActive = False
		self.currTupleId = ("", "", 0)
		self.currCursorIndex, self.currAudioTrack = 0, 0
		self.lastLeftIndex, self.lastRightIndex = 1, 5
		self.mvSrefs, self.channels, self.conferences, self.positions = [], [], [], []
		self.cursor_left, self.cursor_right = None, None
		self["audiotext"] = StaticText()
		self["mvcursor"] = Pixmap()
		self.hideCursor()
		self["mvtext"] = StaticText()
		self.hideMVactive()
		self["key_red"] = StaticText()
		self["key_green"] = StaticText()
		self["key_yellow"] = StaticText()
		self["key_blue"] = StaticText()
		self["exittext"] = StaticText()
		self.startChannel = self.session.nav.getCurrentlyPlayingServiceReference()
		self["actions"] = ActionMap(["WizardActions", "ColorActions", "MenuActions", "NumberActions"], {
			"ok": self.keyOk,
			"1": self.key1,
			"2": self.key2,
			"3": self.key3,
			"4": self.key4,
			"5": self.key5,
			"6": self.key6,
			"7": self.key7,
			"8": self.key8,
			"9": self.key9,
			"back": self.keyExit,
			"left": self.keyLeft,
			"right": self.keyRight,
			"up": self.keyUp,
			"down": self.keyDown,
			"red": self.keyRed,
			"green": self.keyGreen,
			"yellow": self.keyYellowShort,
			"yellowlong": self.keyYellowLong,
			"menu": self.keyMenu,
			"info": self.keyMenu
		}, -1)
		self.audioTimer = eTimer()
		self.audioTimer.callback.append(self.hideAudioText)
		self.exitTimer = eTimer()
		self.exitTimer.callback.append(self.hideExitText)
		self.positions = self.readPositionsFile()
		self.onFirstExecBegin.append(self.startMain)  # session.open() is not allowed before exec

	def startMain(self):
		abort = True
		if self.mvTupleId and self.mvDicts:
			self.currTupleId = self.mvTupleId
			mvSref, mvSname = self.getServiceData(self.mvTupleId)
			if mvSref:
				self.multiviewActive = True
				self.hideAudioText()
				self.hideColorKeys()
				self.hideExitText()
				self.mvInfobox.showDialog(f"Schalte zur Multiview-Übersicht:\n{mvSname}")
				self.channels, self.conferences = self.getMVevents(self.currTupleId)
				pixpath = f"{mvglobals.PLUGINPATH}/pics/{mvglobals.RESOLUTION}/cursor_right.png"
				self.cursor_right = LoadPixmap(cached=True, path=pixpath) if exists(pixpath) else None
				filepath = "cursor_left_4.png" if len(self.channels) < 6 else "cursor_left_8.png"  # max. of 5 simultaneous transmissions, or more?
				pixpath = f"{mvglobals.PLUGINPATH}/pics/{mvglobals.RESOLUTION}/{filepath}"
				self.cursor_left = LoadPixmap(cached=True, path=pixpath) if exists(pixpath) else None
				if self.channels:
					abort = False
					self.session.nav.playService(eServiceReference(mvSref))
					self.show()
					self.showMVactive()
					self.showColorKeys()
					self.showCursor(self.currCursorIndex)
		if abort:
			self.session.openWithCallback(self.abortClosed, MessageBox, "ABBRUCH: Es konnten keine Einzelsendungen zugeordnet werden. Bitte EPG-Daten löschen und frisch auffüllen.", type=MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)
		elif not self.positions:
			posFile = join(mvglobals.PLUGINPATH, "mvcursorpos.cfg")
			self.session.open(MessageBox, f"ABBRUCH: Die Datei\n'{posFile}'\nkonnte nicht gefunden werden", type=MessageBox.TYPE_ERROR, timeout=10, close_on_any_key=True)

	def abortClosed(self, answer=None):
		self.escape()

	def readPositionsFile(self):
		posList = []
		posFile = join(mvglobals.PLUGINPATH, "mvcursorpos.cfg")
		if exists(posFile):
			with open(posFile) as posData:
				for line in posData:
					line = line.split("#")[0].strip()
					if not line:
						continue  # skip comments
					columns = [item.replace("(", "").replace(")", "").strip() for item in line.split(":")[1].split(";")] if ":" in line else []
					posList.append(tuple(tuple(int(int(value.strip()) * (1.5 if mvglobals.RESOLUTION == "FHD" else 1.0)) for value in item.split(",")) for item in columns))
		return posList

	def getMVevents(self, tupleId):
		channels, conferences = [], []
		for mvDict in self.mvDicts:
			if (mvDict.get("mvId", ""), mvDict.get("mvSref", ""), mvDict.get("mvStart", "")) == tupleId:
				channels, conferences = mvDict.get("channels", []), mvDict.get("conferences", [])
				break
		return channels, conferences

	def getServiceData(self, tupleId):
		epgSref, epgSname = "", ""
		for mvDict in self.mvDicts:
			if (mvDict.get("mvId", ""), mvDict.get("mvSref", ""), mvDict.get("mvStart", "")) == tupleId:
				epgSref, epgSname = mvDict.get("mvSref", ""), mvDict.get("mvSname", "")
				break
		return epgSref, epgSname

	def serviceUpdated(self):
		currAudioDict = self.getAudioTracks()
		currTrack = currAudioDict.get("currTrack")
		tracks = currAudioDict.get("tracks", [])
		audioText = tracks[currTrack] if tracks else "keine Audiospuren gefunden"
		audioText = audioText if audioText else "keine Audiospurbenennung gefunden"
		self.showAudioText(audioText)

	def getAudioTracks(self):
		currAudioDict = {}
		currService = self.session.nav.getCurrentService()
		if currService:
			try:
				trackNumber = currService.audioTracks().getNumberOfTracks()
				if trackNumber:
					currAudioDict["tracks"] = []
					for track in range(trackNumber):
						currAudioDict["tracks"].append(currService.audioTracks().getTrackInfo(track).getLanguage())
					currAudioDict["currTrack"] = currService.audioTracks().getCurrentTrack()
			except Exception:
				pass
		return currAudioDict

	def showCursor(self, cursorIndex):
		if self.multiviewActive:
			self["mvcursor"].instance.setPixmap(self.cursor_right if cursorIndex else self.cursor_left)
			maxChannels = len(self.channels) - 1
			if len(self.positions) > maxChannels:
				currPositions = self.positions[maxChannels] if maxChannels < len(self.positions) else []
				xpos, ypos = currPositions[cursorIndex]
				self["mvcursor"].setPosition(xpos, ypos)
				self["mvcursor"].show()
		else:
			self.hideCursor()

	def hideCursor(self):
		self["mvcursor"].hide()

	def showAudioText(self, audioText, timeout=5000):
		self.audioTimer.start(timeout)
		self["audiotext"].setText(audioText)

	def hideAudioText(self):
		self.audioTimer.stop()
		self["audiotext"].setText("")

	def showColorKeys(self):
		self["key_red"].setText("Konferenz 1" if len(self.conferences) > 0 else "")
		self["key_green"].setText("Konferenz 2" if len(self.conferences) > 1 else "")
		self["key_yellow"].setText("Audiokanäle")

	def hideColorKeys(self):
		self["key_red"].setText("")
		self["key_green"].setText("")
		self["key_yellow"].setText("")

	def showExitText(self, exitText, timeout=4000):
		self.exitTimer.start(timeout)
		self["exittext"].setText(exitText)

	def hideExitText(self):
		self.exitTimer.stop()
		self["exittext"].setText("")

	def showMVactive(self):
		self["mvtext"].setText("Multiview")

	def hideMVactive(self):
		self["mvtext"].setText("")

	def keyOk(self):
		if self.multiviewActive:
			self.channelSelect(self.currCursorIndex)
		else:
			self.backToMultiview()

	def keyExit(self):
		if self.multiviewActive:
			self.hideAudioText()
			self.hideColorKeys()
			self.hideExitText()
			self.hideCursor()
			self.hide()
			self.escape()
		else:
			self.backToMultiview()

	def backToMultiview(self):
			epgSref, epgSname = self.getServiceData(self.currTupleId)
			if epgSref:
				self.multiviewActive = True
				self.hideAudioText()
				self.hideColorKeys()
				self.hideExitText()
				self.mvInfobox.showDialog(f"Schalte zurück zur Multiview-Übersicht:\n{epgSname}")
				self.session.nav.playService(eServiceReference(epgSref))
				self.showMVactive()
				self.showColorKeys()
				self.showCursor(self.currCursorIndex)

	def escape(self):
		if self.startChannel:
			self.session.nav.playService(self.startChannel)
		self.multiviewActive = False
		self.close()

	def keyLeft(self):
		if self.multiviewActive:
			if len(self.channels) < 6:
				self.currCursorIndex = 0
			else:  # more than 5 simultaneous transmissions?
				if self.currCursorIndex == 0:  # main cursor
					self.currCursorIndex = self.lastRightIndex
				elif self.currCursorIndex < 5:  # cursor left column
					self.lastLeftIndex = self.currCursorIndex
					self.currCursorIndex = 0
				else:  # cursor right column
					if self.lastLeftIndex == 4:  # last cursor was left column lowest
						self.currCursorIndex = self.lastLeftIndex
					else:
						self.currCursorIndex = (self.currCursorIndex - 4) % len(self.channels)
			self.showCursor(self.currCursorIndex)

	def keyRight(self):
		if self.multiviewActive:
			if len(self.channels) < 6:
				self.currCursorIndex = (self.currCursorIndex + 1) % len(self.channels)
			else:  # more than 5 simultaneous transmissions
				if self.currCursorIndex == 0:  # main cursor
					self.currCursorIndex = self.lastLeftIndex
				elif self.currCursorIndex == 4:  # cursor left column lowest
					self.lastLeftIndex = self.currCursorIndex
					self.currCursorIndex = len(self.channels) - 1
				elif self.currCursorIndex > 4:  # cursor right column
					self.lastRightIndex = self.currCursorIndex
					self.currCursorIndex = 0
				else:  # cursor left column except lowest
					self.currCursorIndex = (self.currCursorIndex + 4) % len(self.channels)
			self.showCursor(self.currCursorIndex)

	def keyUp(self):
		if self.multiviewActive:
			self.currCursorIndex = (self.currCursorIndex - 1) % len(self.channels)
			self.showCursor(self.currCursorIndex)

	def keyDown(self):
		if self.multiviewActive:
			self.currCursorIndex = (self.currCursorIndex + 1) % len(self.channels)
			self.showCursor(self.currCursorIndex)

	def keyRed(self):
		if self.multiviewActive and len(self.conferences) > 0:
			self.hideAudioText()
			self.hideExitText()
			self.hideCursor()
			self.hideMVactive()
			self.multiviewActive = True
			serviceName = self.conferences[0].get("epgSname", "")
			serviceRef = self.conferences[0].get("epgSref", "")
			if serviceRef:
				self.multiviewActive = False
				self.mvInfobox.showDialog(f"Schalte um auf Konferenz 1:\n{serviceName}")
				self.session.nav.playService(eServiceReference(serviceRef))
				self.showExitText("'OK / EXIT' zurück zur Multiview-Übersicht")

	def keyGreen(self):
		if self.multiviewActive and len(self.conferences) > 1:
			self.hideAudioText()
			self.hideExitText()
			self.hideCursor()
			self.hideMVactive()
			self.multiviewActive = True
			serviceName = self.conferences[1].get("epgSname", "")
			serviceRef = self.conferences[1].get("epgSref", "")
			if serviceRef:
				self.multiviewActive = False
				self.mvInfobox.showDialog(f"Schalte um auf Konferenz 2:\n{serviceName}")
				self.session.nav.playService(eServiceReference(serviceRef))
				self.showExitText("'OK / EXIT' zurück zur Multiview-Übersicht")

	def keyYellowShort(self):
		currAudioDict = self.getAudioTracks()
		currTrack = currAudioDict.get("currTrack", 0)
		tracks = currAudioDict.get("tracks", [])
		newTrack = (currTrack + 1) % len(tracks)
		self.session.nav.getCurrentService().audioTracks().selectTrack(newTrack)
		self.serviceUpdated()

	def keyYellowLong(self):
		self.session.openWithCallback(self.keyYellowCB, AudioSelection, infobar=self)

	def keyYellowCB(self, answer):
		self.serviceUpdated()

	def keyMenu(self):
		if self["key_yellow"].getText():
			self.hideColorKeys()
		else:
			self.showColorKeys()

	def key1(self):
		self.channelSelect(0, 1)

	def key2(self):
		self.channelSelect(1, 2)

	def key3(self):
		self.channelSelect(2, 3)

	def key4(self):
		self.channelSelect(3, 4)

	def key5(self):
		self.channelSelect(4, 5)

	def key6(self):
		self.channelSelect(5, 6)

	def key7(self):
		self.channelSelect(6, 7)

	def key8(self):
		self.channelSelect(7, 8)

	def key9(self):
		self.channelSelect(8, 9)

	def channelSelect(self, cursorIndex, numberPressed=0):
		if self.multiviewActive:
			if cursorIndex < len(self.channels):
				if not numberPressed or numberPressed == self.currCursorIndex + 1:
					self.multiviewActive = False
					self.hideCursor()
					self.hideAudioText()
					self.hideColorKeys()
					serviceName = self.channels[cursorIndex].get("epgSname", "")
					serviceRef = self.channels[cursorIndex].get("epgSref", "")
					self.mvInfobox.showDialog(f"Schalte um auf Kanal '{cursorIndex + 1}':\n{serviceName}")
					self.session.nav.playService(eServiceReference(serviceRef))
					self.showExitText("'OK / EXIT' zurück zur Multiview-Übersicht")
				else:
					self.currCursorIndex = cursorIndex
					self.showCursor(cursorIndex)
			else:
				self.mvInfobox.showDialog(f"Kanal '{cursorIndex + 1}' hat zur Zeit keine\nMultiview-Übertragung.")

	def createSummary(self):
		return MVlcdcreen


class MVeventSelect(Screen, MVhelpers):
	skin = """
	<screen name="MVeventSelect" position="center,center" size="1140,680" resolution="1280,720" flags="wfNoBorder" title="Multiview-Eventauswahl" backgroundColor="transparent">
		<widget source="Title" render="Label" position="140,24" size="400,40" font="Regular; 27" textBorderColor="#00505050" textBorderWidth="1" foregroundColor="#00ffff00" backgroundColor="#16000000" valign="center" halign="left" zPosition="12" transparent="1" />
		<widget source="release" render="Label" position="24,658" size="50,20" font="Regular;16" foregroundColor="#005e03" backgroundColor="#000000" valign="center" zPosition="12" transparent="1" halign="center" />
		<widget source="global.CurrentTime" render="Label" position="992,16" size="140,60" font="Regular;46" noWrap="1" halign="center" valign="bottom" foregroundColor="white" backgroundColor="#16000000" cornerRadius="3" zPosition="12" transparent="1">
			<convert type="ClockToText">Default</convert>
		</widget>
		<widget source="global.CurrentTime" render="Label" position="889,22" size="100,26" font="Regular;16" noWrap="1" halign="right" valign="bottom" foregroundColor="white" backgroundColor="#16000000" zPosition="12" transparent="1">
			<convert type="ClockToText">Format:%A</convert>
		</widget>
		<widget source="global.CurrentTime" render="Label" position="889,42" size="100,26" font="Regular;16" noWrap="1" halign="right" valign="bottom" foregroundColor="white" backgroundColor="#16000000" zPosition="12" transparent="1">
			<convert type="ClockToText">Format:%e. %B</convert>
		</widget>
		<eLabel text="von Mr.Servo - Skin von stein17 " position="100,658" size="320,20" font="Regular;16" foregroundColor="#005e03" backgroundColor="#000000" transparent="1" zPosition="2" halign="left" />
		<eLabel name="fullscreen_bg" position="0,80" size="1140,600" backgroundColor="#16002a01,#16010001,#16000000,vertical" zPosition="-8" />
		<eLabel name="title_bg" position="0,10" size="1140,78" backgroundColor="#16008c03,#16002a01,#16000000,horizontal" zPosition="-9" cornerRadius="12" />
		<eLabel name="line" position="0,78" size="1140, 2" backgroundColor="#002a01,#008c03,#002a01,horizontal" zPosition="2" />
		<eLabel name="line" position="16,272" size="1088, 1" backgroundColor="#002a01,#008c03,#002a01,horizontal" zPosition="2" />
		<eLabel name="line" position="16,464" size="1088, 1" backgroundColor="#002a01,#008c03,#002a01,horizontal" zPosition="2" />
		<eLabel name="line" position="16,656" size="1088, 1" backgroundColor="#002a01,#008c03,#002a01,horizontal" zPosition="2" />
		<ePixmap pixmap="~plugin.png" position="16,26" size="100,40" alphatest="blend" transparent="1" zPosition="2"/>
		<widget source="menulist" render="Listbox" position="10,80" size="1120,576" enableWrapAround="1" backgroundColor="#15151515" foregroundColor="#dbe1e4" itemCornerRadiusSelected="12" itemGradientSelected="#008c03,#002a01,#002a01,horizontal"
		foregroundColorSelected="#d7d7d7" backgroundColorSelected="#16008c03" scrollbarMode="showOnDemand" scrollbarBorderWidth="1" scrollbarWidth="10" scrollbarBorderColor="#007302" scrollbarForegroundColor="#002c01" transparent="1">
			<convert type="TemplatedMultiContent">{"template": [  # index 0 ('mvSref') is not used in skin!
				MultiContentEntryPixmapAlphaBlend(pos=(10,12), size=(36,36), flags=BT_HALIGN_LEFT|BT_VALIGN_CENTER, png=13),  # logos
				MultiContentEntryText(pos=(60,16), size=(380,30), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP|RT_WRAP, text=7),  # mvCountdown
				MultiContentEntryText(pos=(60,16), size=(60,30), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP|RT_WRAP, text=3),  # progessStart
				MultiContentEntryProgress(pos=(124,24), size=(130,10), borderWidth=1, foreColor=0xcbcbcb, percent=-5),  # mvProgress
				MultiContentEntryText(pos=(270,16), size=(60,30), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP|RT_WRAP, text=4),  # progessEnd
				MultiContentEntryText(pos=(340,16), size=(120,30), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP|RT_WRAP, text=6),  # mvRemaining
				MultiContentEntryPixmapAlphaBlend(pos=(10,54), size=(90,54), flags=BT_HALIGN_LEFT|BT_VALIGN_CENTER|BT_SCALE, png=12),  # picons
				MultiContentEntryText(pos=(112,64), size=(330,38), font=0, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP, text=1),  # mvSname
				MultiContentEntryText(pos=(12,112), size=(520,30), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP, text=2),  # mvEvent
				MultiContentEntryText(pos=(12,142), size=(400,30), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_TOP|RT_WRAP, text=8),  # mvTimeline
				MultiContentEntryText(pos=(540,0), size=(580,180), font=1, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER , text=9),  # mvc_large
				MultiContentEntryText(pos=(540,0), size=(580,180), font=2, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER , text=10),  # mvc_medium
				MultiContentEntryText(pos=(540,0), size=(580,180), font=3, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER , text=11),  # mvc_small
				],
					"fonts": [gFont("Regular",27), gFont("Regular",22), gFont("Regular",18), gFont("Regular",15)],
					"itemHeight":192
					}
			</convert>
		</widget>
	</screen>
	"""
	nameMap = {"FCBayernMünchen": "BayernMünchen", "FCBayern": "BayernMünchen", "BorussiaM'Gladbach": "BorussiaMönchengladbach",
			"FCSchalke04": "Schalke04", "FCIngolstadt04": "FCIngolstadt", "SCPaderborn07": "FCPaderborn", "BVB": "BorussiaDortmund"
			}
	iconMap = {"bl": "liveBL.png", "BuLi": "liveBL.png", "CL": "liveBL.png", "league": "liveBL.png", "fifa": "liveBL.png", "uefa": "liveBL.png",
			"tennis": "liveTennis.png", "atp": "liveTennis.png", "wta": "liveTennis.png", "davis": "liveTennis.png",
			"fed": "liveTennis.png", "open": "liveTennis.png", "wimbleton": "liveTennis.png",
			"f1": "liveF1.png", "formel1": "liveF1.png", "formel-1": "liveF1.png",
			"golf": "liveGolf.png", "pga": "liveGolf.png", "ryder": "liveGolf.png", "fedex": "liveGolf.png", "wgc": "liveGolf.png"
			}

	def __init__(self, session):
		self.skin = self.skin.replace("~", f"{mvglobals.PLUGINPATH}/pics/{mvglobals.RESOLUTION}/")
		Screen.__init__(self, session)
		self._instance = eEPGCache.getInstance()
		self.refreshTimer = eTimer()
		self.mvInfobox = session.instantiateDialog(MVinfoBox)
		self.mvDicts = []
		self["release"] = StaticText(mvglobals.RELEASE)
		self["headline"] = StaticText("Starte laufende Multiview Veranstaltung:")
		self["menulist"] = List()
		self["actions"] = ActionMap(["OkCancelActions"], {
			"ok": self.keyOk,
			"cancel": self.keyExit
		}, -1)
		self.refreshTimer.callback.append(self.refreshMenulist)
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self["menulist"].setList([])
		callInThread(self.refreshMenulist)

	def refreshMenulist(self):
		def countDownText(durance):
			countdown = ""
			if durance:
				mins, secs = divmod(durance, 60)
				hours, mins = divmod(mins, 60)
				days, hours = divmod(hours, 24)
				if days or hours or mins > 1:
					countdown += "noch "
					dayType = "Tag" if days == 1 else "Tage"
					countdown += f"{int(days)} {dayType}, " if days else ""
					countdown += f"{int(hours)} Stunden, " if hours else ""
					countdown += f"{int(mins)} Minuten"
				else:
					countdown += "startet gleich..."
			return countdown

		self.refreshTimer.startLongTimer(30)
		self.mvDicts = self.getEPGmvDicts()
		menuList = []
		if self.mvDicts:
			nowTs = datetime.now(tz=None).timestamp()
			for mvDict in self.mvDicts:
				mvId = mvDict.get("mvId", "")
				mvSname = mvDict.get("mvSname", "")
				mvEvent = mvDict.get("mvEvent", "").replace(":", ": ").replace(",", ", ").replace(".", ". "). replace("Multiview", "")
				mvEvent = ",".join(mvEvent.split(",")[:2])
				mvStart = mvDict.get("mvStart", 0)
				mvDurance = mvDict.get("mvDurance", 0)
				mvEnd = mvStart + mvDurance
				mvSref = mvDict.get("mvSref", "")
				mvTupleId = (mvId, mvSref, mvStart)
				if nowTs > mvStart and nowTs < mvEnd:  # enable progressbar and start/end, disable countdown, show logo 'running'
					progressStart = datetime.fromtimestamp(mvStart).strftime("%H:%M")
					progressEnd = datetime.fromtimestamp(mvEnd).strftime("%H:%M")
					mvRemaining = f"+{int((mvEnd - nowTs) / 60)} Min" if nowTs > mvStart and nowTs < mvEnd else ""
					mvProgress = int((nowTs - mvStart) / (mvEnd - mvStart) * 100)
					mvCountdown = ""
					logoFile = "pics/{mvglobals.RESOLUTION}/live.png"
					for key, iconFile in self.iconMap.items():
						if key and key in mvId.lower():
							logoFile = join(mvglobals.PLUGINPATH, f"pics/{mvglobals.RESOLUTION}/{iconFile}.png")
							break
					logoPix = LoadPixmap(cached=True, path=logoFile) if logoFile and exists(logoFile) else None
				else:  # disable progressbar and time, enable countdown, show logo 'not running'
					progressStart, progressEnd, mvRemaining, mvProgress = "", "", "", -1
					mvCountdown = countDownText(mvStart - nowTs)
					logoFile = join(mvglobals.PLUGINPATH, f"pics/{mvglobals.RESOLUTION}/no_live.png")
					logoPix = LoadPixmap(cached=True, path=logoFile) if logoFile and exists(logoFile) else None
				channelRes = search(r'\d+', mvSname)
				channelNo = int(channelRes.group()) if channelRes else 0
				piconFile = join(mvglobals.PLUGINPATH, f"pics/{mvglobals.RESOLUTION}/buli{channelNo}.png")
				if not piconFile or not exists(piconFile):  # fallback to standard picon
					piconFile = join(mvglobals.PLUGINPATH, f"{getPiconName(mvSref)}.png")
				piconPix = LoadPixmap(cached=True, path=piconFile) if piconFile and exists(piconFile) else None
				mvChannels, mvConferences = [], []
				for index, channel in enumerate(mvDict.get("channels", [])):
					# e.g. 'LiveBL:RBLeipzig-VfBStuttgart,9.Spieltag'
					mvChannels.append(f"Sendung {index + 1}: {channel.get('epgTitle', '').split(':')[1].split(',')[0].replace('-', ' - ')}")
				if not mvChannels:
					mvChannels = ["{keine Einzelsendung gefunden}"]
				for index, conference in enumerate(mvDict.get("conferences", [])):
					# e.g. 'Fußball:2.Bundesliga,AlleSpiele,alleToreDieVodafoneHighlight-Show,11.Spieltag,Samstag'
					mvConferences.append(f"Konferenz: {conference.get('epgTitle', '').split(':')[1].split(',')[0].replace('-', ' - ')}")
				if not mvConferences:
					mvConferences = ["{keine Konferenz gefunden}"]
				mvCommon = "\n".join(mvChannels + mvConferences)
				mvc_large, mvc_medium, mvc_small = "", "", ""
				lenChannels = len(mvChannels)
				match True:
					case _ if lenChannels < 6:
						mvc_large = mvCommon
					case _ if lenChannels < 8:
						mvc_medium = mvCommon
					case _:
						mvc_small = mvCommon
				mvStartDt = datetime.fromtimestamp(mvStart)
				mvStartStr = mvStartDt.strftime("%H:%M Uhr")
				isToday = datetime.fromtimestamp(nowTs).date() != mvStartDt.date()
				mvWeekday = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][mvStartDt.weekday()] if isToday else "heute"
				mvDuranceStr = f"Dauer: {int(mvDurance / 60)} Minuten"
				mvTimeline = f"{mvWeekday}, {mvStartStr}, {mvDuranceStr}"
				menuList.append((mvSref, mvSname, mvEvent, progressStart, progressEnd, mvProgress, mvRemaining, mvCountdown, mvTimeline, mvc_large, mvc_medium, mvc_small, piconPix, logoPix, mvTupleId))
		else:
			mvChannels = "{keine Einzelsendung gefunden}\n{keine Konferenz gefunden}"
			menuList.append(("", "kein Multiview gefunden", "", "", "", -1, "", "", "", mvChannels, "", "", None, None, None))
		self["menulist"].updateList(menuList)

	def keyOk(self):
		current = self["menulist"].getCurrent()
		if current and self.mvDicts:
			self.refreshTimer.stop()
			self.session.open(MVmain, current[-1], self.mvDicts, self.mvInfobox)  # [-1] is mvTupleId

	def keyExit(self):
		self.refreshTimer.stop()
		self.session.deleteDialog(self.mvInfobox)
		self.close()


class MVinfoBox(Screen):
	skin = """
	<screen name="MVinfoBox" position="390,432" size="500,110" flags="wfNoBorder" resolution="1280,720" title="Sky Multiview Infobox">
		<eLabel position="0,0" size="500,110" backgroundColor="#002a01,#008c03,#002a01,horizontal" zPosition="-1"/>
		<eLabel position="2,2" size="496,106" zPosition="-1"/>
		<widget source="info" render="Label" position="5,5" size="490,100" font="Regular;24" halign="center" valign="center"/>
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["info"] = StaticText()
		self.isVisible = False
		self.mvinfoTimer = eTimer()
		self.mvinfoTimer.callback.append(self.hideDialog)

	def showDialog(self, info, timeout=1500):
		self["info"].setText(info)
		self.isVisible = True
		self.show()
		if timeout:
			self.mvinfoTimer.start(timeout, True)

	def hideDialog(self):
		self.mvinfoTimer.stop()
		self.isVisible = False
		self.hide()

	def getIsVisible(self):
		return self.isVisible


class MVlcdcreen(Screen):
	skin = """
	<screen position="0,0" size="320,240" title="Sky Multiview">
		<widget source="lcdanz1" render="Label" position="0,0" size="320,115" font="Regular;14" halign="left" valign="top"/>
		<widget source="lcdanz2" render="Label" position="0,125" size="320,115" font="Regular;14" halign="center" valign="bottom"/>
	</screen>
	"""

	def __init__(self, session, parent):
		Screen.__init__(self, session)
		self["lcdanz1"] = StaticText("Sky Multiview Plugin")
		self["lcdanz2"] = StaticText("Screen: Multiview LCDScreen")


def main(session, **kwargs):
	session.open(MVeventSelect)


def Plugins(**kwargs):
	icon = f"pics/{mvglobals.RESOLUTION}/plugin.png"
	return [
			PluginDescriptor(name="Sky Multiview", description=f"Bedienoberfläche Sky Multiview {mvglobals.RELEASE}", where=[PluginDescriptor.WHERE_PLUGINMENU], icon=icon, fnc=main),
			PluginDescriptor(name="Sky Multiview", description=mvglobals.RELEASE, where=[PluginDescriptor.WHERE_EXTENSIONSMENU], fnc=main)
			]
