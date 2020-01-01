#!/usr/bin/env python3

import sys, smtplib, ssl, keyring, os, logging, time
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu, QAction, QDialog, QFileDialog
from PyQt5.QtGui import QIcon, QTextCursor, QIntValidator
from PyQt5.QtCore import QUrl, QTimer, QSettings, QObject, QRunnable, QThreadPool, pyqtSignal
from PySteamTrades.Ui_MainWindow import *
from PySteamTrades.Ui_PrefsDialog import *
from PySteamTrades.Ui_TestDialog import *

baseDir = None
readIcon = None
unreadIcon = None

defaultInterval = 5
defaultLevel = 2
defaultLogfile = 'PySteamTrades.log'
logFormat = '%(asctime)s - %(thread)d - %(levelname)s: %(message)s'
stUrl = QUrl('https://www.steamtrades.com/messages')

logLevels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]
orgName = 'PySteamTrades'
appName = 'PySteamTrades'
sysName = "{}-{}".format(orgName, appName)

messageTemplate = """\
Subject: New message on SteamTrades
From: {sender}
To: {recipient}

You have {count} new message(s)

New message from {author}:
{message}
"""

testTemplate = """\
Subject: PySteamTrades test message
From: {sender}
To: {recipient}

PySteamTrades test message
"""

class Emitter(QObject):
    error = pyqtSignal(str, str)

class MailSender(QRunnable):
    def __init__(self, sender, recipient, smtpServer, smtpPort, encryption,\
    username, password, message, permalink = '', debug = False):
        super().__init__()
        self.sender = sender
        self.recipient = recipient
        self.smtpServer = smtpServer
        self.smtpPort = smtpPort
        self.encryption = encryption
        self.username = username
        self.password = password
        self.message = message
        self.permalink = permalink
        self.debug = debug
        self.emitter = Emitter()
    def run(self):
        server = None
        try:
            context = ssl.create_default_context()
            if self.encryption == 'SSL':
                server = smtplib.SMTP_SSL(self.smtpServer, self.smtpPort, timeout=30, context=context)
            else:
                server = smtplib.SMTP(self.smtpServer, self.smtpPort, timeout=30)
            if self.debug:
                server.set_debuglevel(1)
            if self.encryption == 'TLS':
                server.starttls(context=context)
            if self.username != '':
                server.login(self.username, self.password)
            server.sendmail(self.sender, self.recipient, self.message.encode("utf8"))
        except Exception as e:
            logging.error('Error sending email: ' + str(e))
            self.emitter.error.emit('Error sending email: ' + str(e), self.permalink)
        try:
            if server:
                server.quit()
        except:
            pass

class TestDialog(QDialog):
    newMessage = pyqtSignal(str)
    def __init__(self, parent, mailSender):
        super().__init__(parent)
        self.ui = Ui_TestDialog()
        self.ui.setupUi(self)
        self.mailSender = mailSender
        self.newMessage.connect(self.logMessage)
        self.mailSender.emitter.error.connect(self.logMessage)
    def showEvent(self, event):
        super().showEvent(event)
        # redirect stderr to self.write, to capture debug output of sendmail
        self.stderr = sys.stderr
        sys.stderr = self
        QThreadPool.globalInstance().start(self.mailSender)
    def closeEvent(self, event):
        sys.stderr = self.stderr
        event.accept()
    def write(self, message):
        # update logTextEdit from the GUI thread
        self.newMessage.emit(message)
    def logMessage(self, message):
        self.ui.logTextEdit.moveCursor(QTextCursor.End)
        self.ui.logTextEdit.insertPlainText(message)

class PrefsDialog(QDialog):
    intervalChanged = pyqtSignal(int)
    loglevelChanged = pyqtSignal(int)
    logfileChanged = pyqtSignal()
    def __init__(self, parent):
        super().__init__(parent)
        self.ui = Ui_PrefsDialog()
        self.ui.setupUi(self)

        self.ui.okButton.clicked.connect(self.accept)
        self.ui.testButton.clicked.connect(self.testSettings)
        self.ui.logfileButton.clicked.connect(self.selectFile)

        validator = QIntValidator(1, 65535, self)
        self.ui.portLineEdit.setValidator(validator)

        s = QSettings(orgName, appName)

        self.ui.intervalSpinBox.setValue(s.value('misc/interval', defaultInterval, type = int))
        self.ui.loglevelComboBox.setCurrentIndex(s.value('misc/loglevel', defaultLevel, type = int))
        self.ui.logGroupBox.setChecked(True if s.value('logfile/enable', False, type=bool) else False)
        self.ui.logfileLineEdit.setText(s.value('logfile/filename', defaultLogfile))

        self.ui.emailGroupBox.setChecked(True if s.value('email/notify', False, type=bool) else False)
        self.ui.encryptionGroupBox.setChecked(True if s.value('email/encrypt', False, type=bool) else False)
        self.ui.loginGroupBox.setChecked(True if s.value('email/login', False, type=bool) else False)

        self.ui.senderLineEdit.setText(s.value('email/sender'))
        self.ui.recipientLineEdit.setText(s.value('email/recipient'))
        self.ui.hostLineEdit.setText(s.value('email/host'))
        self.ui.portLineEdit.setText(s.value('email/port'))

        self.ui.encryptionComboBox.setCurrentText(s.value('email/encryption_type'))

        self.ui.usernameLineEdit.setText(s.value('email/username'))
        try:
            self.ui.passwordLineEdit.setText(keyring.get_password(sysName,  "email/password"))
        except Exception as e:
            logging.warning('Cannot read password from keyring: ' + str(e))
    def selectFile(self):
        filename, _ = QFileDialog.getSaveFileName(self, 'Log file name', self.ui.logfileLineEdit.text(), "Log file (*.log);;All files(*.*)")
        if filename:
            self.ui.logfileLineEdit.setText(filename)
    def testSettings(self):
        mailSender = MailSender(self.ui.senderLineEdit.text(), self.ui.recipientLineEdit.text(),\
        self.ui.hostLineEdit.text(), self.ui.portLineEdit.text(),\
        self.ui.encryptionComboBox.currentText() if self.ui.encryptionGroupBox.isChecked() else '',\
        self.ui.usernameLineEdit.text() if self.ui.loginGroupBox.isChecked() else '',\
        self.ui.passwordLineEdit.text() if self.ui.loginGroupBox.isChecked() else '',\
        testTemplate.format(sender = self.ui.senderLineEdit.text(),  recipient = self.ui.recipientLineEdit.text()), '', True)
        testDialog = TestDialog(self,  mailSender)
        testDialog.exec_()
    def accept(self):
        s = QSettings(orgName, appName)

        newInterval = self.ui.intervalSpinBox.value()
        if s.value('misc/interval', type = int) != newInterval:
            s.setValue('misc/interval', newInterval)
            self.intervalChanged.emit(newInterval)

        newLevel = self.ui.loglevelComboBox.currentIndex()
        if s.value('misc/loglevel', defaultLevel, type = int) != newLevel:
            s.setValue('misc/loglevel', newLevel)
            self.loglevelChanged.emit(newLevel)

        if s.value('logfile/enable', False, type = bool) != self.ui.logGroupBox.isChecked()\
        or s.value('logfile/filename') != self.ui.logfileLineEdit.text():
            s.setValue('logfile/enable', self.ui.logGroupBox.isChecked())
            s.setValue('logfile/filename', self.ui.logfileLineEdit.text())
            self.logfileChanged.emit()

        s.setValue('email/notify', self.ui.emailGroupBox.isChecked())
        s.setValue('email/encrypt', self.ui.encryptionGroupBox.isChecked())
        s.setValue('email/login', self.ui.loginGroupBox.isChecked())

        s.setValue('email/sender',  self.ui.senderLineEdit.text())
        s.setValue('email/recipient',  self.ui.recipientLineEdit.text())
        s.setValue('email/host',  self.ui.hostLineEdit.text())
        s.setValue('email/port',  self.ui.portLineEdit.text())

        s.setValue('email/encryption_type',  self.ui.encryptionComboBox.currentText())

        s.setValue('email/username',  self.ui.usernameLineEdit.text())
        try:
            keyring.set_password(sysName,  "email/password", self.ui.passwordLineEdit.text())
        except Exception as e:
            logging.error('Cannot save password to keyring: ' + str(e))
        super().accept()

class Handler(QObject, logging.Handler):
    newMessage = pyqtSignal(str)
    def emit(self, record):
        msg = self.format(record)
        self.newMessage.emit(msg)
    def write(self, msg):
        pass

class MainWindow(QMainWindow):
    error = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setWindowIcon(readIcon)
        # permalinks of comments we already notified the user of
        self.permalinks = []
        self.quitting = False
        self.error.connect(self.showError)
        # Logger
        self.fileHandler = None
        self.handler = Handler()
        self.handler.newMessage.connect(self.logMessage)
        s = QSettings(orgName, appName)
        level = s.value('misc/loglevel', defaultLevel, type = int)
        self.handler.setLevel(logLevels[level])
        self.handler.setFormatter(logging.Formatter(logFormat))
        logging.getLogger().addHandler(self.handler)
        self.updateLogger()
        # Tray icon
        self.ui.prefsAction.triggered.connect(self.showPrefs)
        self.ui.refreshAction.triggered.connect(self.refresh)
        self.ui.quitAction.triggered.connect(self.quit)
        minimizeAction = QAction("Mi&nimize",  self)
        minimizeAction.triggered.connect(self.hide)
        restoreAction = QAction("&Restore",  self)
        restoreAction.triggered.connect(self.show)
        trayMenu = QMenu(self)
        trayMenu.addAction(minimizeAction)
        trayMenu.addAction(restoreAction)
        trayMenu.addAction(self.ui.prefsAction)
        trayMenu.addAction(self.ui.refreshAction)
        trayMenu.addAction(self.ui.quitAction)
        self.trayIcon = QSystemTrayIcon()
        self.trayIcon.setContextMenu(trayMenu)
        self.trayIcon.activated.connect(self.iconActivated)
        self.trayIcon.setIcon(readIcon)
        self.trayIcon.setVisible(True)
        self.ui.webView.loadFinished.connect(self.loadFinished)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.updateInterval(s.value('misc/interval', defaultInterval, type = int))
        self.timer.start()
        self.refresh()
    def logMessage(self, msg):
        self.ui.logTextEdit.appendPlainText(msg)
    def updateLogLevel(self, newLevel):
        logging.debug('setting log level ' + str(newLevel))
        logging.getLogger().setLevel(logLevels[newLevel])
        for h in logging.getLogger().handlers:
            h.setLevel(logLevels[newLevel])
    def updateLogger(self):
        logging.debug("updating logger handlers")
        s = QSettings(orgName, appName)
        if self.fileHandler:
            logging.getLogger().removeHandler(self.fileHandler)
            self.fileHandler = None
        if s.value('logfile/enable', False, type = bool):
            f = s.value('logfile/filename', defaultLogfile)
            if not os.path.isabs(f):
                f = os.path.join(baseDir, f)
            logging.debug('new file handler for ' + f)
            fileHandler = logging.FileHandler(f)
            level = s.value('misc/loglevel', defaultLevel, type = int)
            fileHandler.setLevel(logLevels[level])
            fileHandler.setFormatter(logging.Formatter(logFormat))
            self.fileHandler = fileHandler
            logging.getLogger().addHandler(self.fileHandler)
    def refresh(self):
        self.ui.webView.setUrl(stUrl)
    def updateInterval(self, newInterval):
        logging.info('setting refresh interval: {} minutes'.format(newInterval))
        self.timer.setInterval(newInterval * 1000 * 60)
    def quit(self):
        self.trayIcon.setVisible(False)
        self.quitting = True
        QApplication.setQuitOnLastWindowClosed(True)
        self.close()
    def loadFinished(self, ok):
        if ok == False:
            logging.warning('failed to load URL: ' + self.ui.webView.url().toString())
            return
        self.ui.webView.page().toHtml(self.checkPage)
    def closeEvent(self,  event):
        if not self.quitting:
            self.hide()
            event.ignore()
        else:
            event.accept()
    def iconActivated(self,  reason):
        if reason == QSystemTrayIcon.Context or reason == QSystemTrayIcon.Trigger:
            return
        if self.isVisible():
            self.hide()
        else:
            self.show()
    def showPrefs(self):
        d = PrefsDialog(self)
        d.intervalChanged.connect(self.updateInterval)
        d.loglevelChanged.connect(self.updateLogLevel)
        d.logfileChanged.connect(self.updateLogger)
        d.exec_()
    def showError(self, message):
        self.trayIcon.showMessage('', message, QSystemTrayIcon.Warning)
    def onMailError(self, msg, permalink):
        self.showError(msg)
        if permalink in self.permalinks:
            self.permalinks.remove(permalink)
    def checkPage(self,  page):
        url = self.ui.webView.url()
        self.statusBar().showMessage(url.toString())
        logging.info('loaded page ' + url.toString())
        soup = BeautifulSoup(page, 'html.parser')
        if url.host() == 'www.steamtrades.com' or url.host() == 'steamtrades.com':
            if '<span>Messages' not in page:
                logging.warning('log in to SteamTrades to receive message notifications')
                self.error.emit('log in to SteamTrades to receive message notifications')
                return
        if url != stUrl:
            return
        messageCount = soup.find('span', attrs={'class': 'message_count'})
        if not messageCount:
            self.trayIcon.setIcon(readIcon)
            self.setWindowIcon(readIcon)
            return

        logging.debug('message count:' + messageCount.text)

        self.trayIcon.setIcon(unreadIcon)
        self.setWindowIcon(unreadIcon)
        try:
            parsed = 0
            for comment in soup.find_all('div', attrs={'class': 'comment_inner'}):
                if parsed >= int(messageCount.text):
                    break
                if comment.find('div', attrs={'class': 'comment_unread'}) == None:
                    continue
                parsed += 1
                author = comment.find('a', attrs={'class': 'author_name'}).text.strip()
                message = comment.find('div', attrs={'class': 'comment_body_default markdown'}).text.strip()
                permalink = comment.find_all('a')[-1]['href']
                if permalink not in self.permalinks:
                    logging.debug('unread comment: \n' + str(comment))
                    logging.debug('author: ' + author)
                    logging.debug('message: \n' + message)
                    logging.debug('permalink:' + permalink)
                    self.trayIcon.showMessage("New message from " + author,  message)
                    s = QSettings(orgName, appName)
                    if s.value('email/notify', False, type=bool):
                        sender = s.value('email/sender')
                        recipient =s.value('email/recipient')
                        smtpServer = s.value('email/host')
                        smtpPort = s.value('email/port')
                        encryption = s.value('email/encryption_type') if s.value('email/encrypt', False, type=bool) else ''
                        username = s.value('email/username') if s.value('email/login', False, type=bool) else ''
                        password = ''
                        try:
                            if s.value('email/login', False, type=bool):
                                password = keyring.get_password(sysName,  "email/password")
                        except Exception as e:
                            logging.warning('Cannot read password from keyring: ' + str(e))
                        mailSender = MailSender(sender, recipient, smtpServer, smtpPort, encryption, username, password,\
                        messageTemplate.format(sender = sender,  recipient = recipient, count = messageCount.text, author = author, message = message), permalink)
                        logging.info('sending email...')
                        mailSender.emitter.error.connect(self.onMailError)
                        QThreadPool.globalInstance().start(mailSender)
                    self.permalinks.append(permalink)
        except Exception as e:
            logging.error(str(e))
            self.error.emit(str(e))

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        baseDir = sys._MEIPASS
    else:
        baseDir = os.path.dirname(os.path.realpath(__file__))
    app = QApplication(sys.argv)
    s = QSettings(orgName, appName)
    level = s.value('misc/loglevel', defaultLevel, type = int)
    logging.basicConfig(format=logFormat, level=logLevels[level])
    if sys.stderr == None:
        logging.getLogger().handlers.clear()
    QApplication.setQuitOnLastWindowClosed(False)
    readIcon = QIcon(baseDir + '/read.ico')
    unreadIcon = QIcon(baseDir + '/unread.ico')
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
