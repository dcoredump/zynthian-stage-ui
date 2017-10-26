#!/usr/bin/python3
"""
Zynthian stage gui
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.app import App
from kivy.properties import ObjectProperty
from kivy.properties import NumericProperty
from kivy.uix.listview import ListItemButton
from kivy.adapters.models import SelectableDataItem
from kivy.logger import Logger
from kivy.clock import Clock
import os, stat, sys, re
import subprocess
import shlex
import pwd
import jack
from time import sleep
from pprint import pprint
from pathlib import Path

##############################################################################
# Globals
##############################################################################

PEDALBOARDS_PATH = os.environ['HOME'] + "/.pedalboards"
PEDALBOARD2MODHOST = "./pedalboard2modhost"
JACKWAIT="/usr/local/bin/jack_wait -t1 -w"
JACKALIAS="/usr/local/bin/jack_alias"
SYSTEMCTL="/bin/systemctl"
MODHOST_PIPE="/tmp/mod-host"
LAST_PEDALBOARD_FILE=os.environ['HOME'] + "/.last_pedalboard"

client=None
xrun_counter=0
actual_pedalboard="default"

##############################################################################
# Kivy class
##############################################################################

class StageApp(App):
    pass

class StageRoot(BoxLayout):
    pass

class ListPedalboardButton(ListItemButton):
   pass

class DataItem(SelectableDataItem):
    def __init__(self, text="", is_selected=False):
        self.text = text
        self.is_selected = is_selected

class StageScreens(BoxLayout):
    global xrun_counter
    modui_button=ObjectProperty()
    jack_button=ObjectProperty()
    preset_list=ObjectProperty()
    mod_host_status=ObjectProperty()

    def set_modui_button_state(self):
        if(systemctlstatus('mod-ui')==True and systemctlstatus('jack2')==True):
            return("down")
        else:
            return("normal")

    def change_modui_button_state(self):
        if(systemctlstatus('mod-ui')==True):
            mod_service("mod-ui",False)
            mod_service("mod-host",False)
            mod_service("mod-host-pipe",True)
        else:
            mod_service("mod-host-pipe",False)
            mod_service("mod-host",True)
            mod_service("mod-ui",True)

    def restart_jack(self):
        global actual_pedalboard
        mod_service("mod-ui",False)
        mod_service("mod-host",False)
        self.modui_button.state='normal'
        systemctl("jack2",False)
        startup_jack()
        actual_pedalboard=read_last_pedalboard()
        load_pedalboard(actual_pedalboard,init=True)

##############################################################################
# Functions
##############################################################################

def list_items_args_converter(row_index, obj):
    return({'text': obj.text, 'size_hint_y': None, 'height': 50})

def get_pedalboard_names():
    actual_pedalboard=read_last_pedalboard()
    pedalboards = []
    for p in os.listdir(PEDALBOARDS_PATH):
        m = re.search("^(.+)\.pedalboard", p)
        if (m):
            if(m.group(1)==actual_pedalboard):
                Logger.info("get_pedalboard_names: found actual pedalboard [%s]" % actual_pedalboard)
                pedalboards.append(DataItem(text=m.group(1),is_selected=True))
            else:
                pedalboards.append(DataItem(text=m.group(1)))
    return (pedalboards)

def load_pedalboard(pedalboard, init=False):
    global actual_pedalboard

    Logger.info("load_pedalboard:%s" % pedalboard)

    if(actual_pedalboard==pedalboard and init==False):
        Logger.info("load_pedalboard:no need to load the same pedalboard")
        return
    if(systemctlstatus("mod-ui")):
        Logger.info("load_pedalboard:mod-ui is running! Loading nothing")
        return

    mod_service("mod-host",False)
    mod_service("mod-host-pipe",False)
    mod_service("mod-host-pipe",True)
   
    if(systemctlstatus('mod-host-pipe') and systemctlstatus('jack2')):
        if (pedalboard == "default"):
            pedalboard_ttl_name = "Default.ttl"
        else:
            pedalboard_ttl_name = pedalboard + ".ttl"
        if (stat.S_ISFIFO(os.stat(MODHOST_PIPE).st_mode)):
            if (subprocess.call("echo \"remove -1\" >" + MODHOST_PIPE, shell=True)==0):
                Logger.info("load_pedalboard:Cleanup pedalboard.")
            else:
                Logger.warning("Cleanup pedalboard failed.")

            if (subprocess.call(PEDALBOARD2MODHOST + " " + PEDALBOARDS_PATH + "/" + pedalboard + ".pedalboard/" + pedalboard_ttl_name + " > " + MODHOST_PIPE, shell=True)==0):
                Logger.info("load_pedalboard:Pedalboard "+pedalboard+" load success.")
                write_last_pedalboard(pedalboard)
                sleep(3)
            else:
                Logger.warning("Pedalboard "+pedalboard+" load problem.")
        else:
            Logger.warning(MODHOST_PIPE + " is not a named pipe.")
    else:
        Logger.warning("Loading of pedalboards is disabled during a running mod-ui.")

def mod_service(mod,state):
    if(systemctlstatus(mod)!=state):
        if(state==True):
            systemctl(mod,True)
        else:
            systemctl(mod,False)
        Logger.info("mod_service:State change for %s to %s" % (mod,state))
    else:
        Logger.info("mod_service:No state change for %s" % mod)

def check_jack():
    Logger.info("check_jack:")
    jackwait=subprocess.call(JACKWAIT+">/dev/null 2>&1",shell=True)
    if(jackwait!=0):
        return(False)
    else:
        return(True)

def systemctlstatus(service):
    if(subprocess.call(shlex.split(SYSTEMCTL + " status "+service))!=0):
        return(False)
    else:
        return(True)

def systemctl(service,run):
    Logger.info("systemctl: %s %s" % (service,run))
    if(run==True):
        if(subprocess.call(shlex.split(SYSTEMCTL + " start "+service))!=0):
            Logger.error("Cannot start %s" % service)
            return(False)
        else:
            return(True)
    else:
        if(subprocess.call(shlex.split(SYSTEMCTL + " stop "+service))!=0):
            Logger.error("Cannot stop %s" % service)
            return(False)
        else:
            return(True)

def quit_prog():
    global client
    mod_service("mod-ui",False)
    mod_service("mod-host",False)
    mod_service("mod-host-pipe",False)
    midi_alias(unalias=True)
    exit(0)

def halt():
    subprocess.call("/sbin/halt",shell=True)
    exit(0)

def restart():
    subprocess.call("/sbin/reboot",shell=True)
    exit(0)

def get_username():
    return pwd.getpwuid(os.getuid())[0]

def xrun(delay):
    global xrun_counter
    Logger.warn("jackd: XRUN[%d] delay=%d" % (xrun_counter,delay))
    xrun_counter=xrun_counter+1
 
def jack_status(status, reason):
    global jack_status_message
    Logger.warn("jackd: '%s'" % reason)
    jack_status_message=(status, reason)

def startup_jack():
    global xrun_counter

    Logger.info("startup_jack:")

    mod_service("mod-ui",False)
    mod_service("mod-host",False)

    xrun_counter=0

    while True:
        if(check_jack()==False):
            if(systemctl("jack2",True)==False):
                Logger.critical("jackd is not running")
                exit(101)
                if(systemctl("mod-host-pipe",True)==False):
                    Logger.critical("mod-host-pipe is not running")
                    exit(101)
                Logger.info("startup_jack:mod-host-pipe was not running, started.")
            else:
                break
        else:
            break

def midi_alias(unalias=False):
    global client
    if(client==None):
        Logger.warning("No internal jack-client available, creating new one...")
        client=jack.Client("stage")
    for i in range(1,3):
        if(i%2==0):
            io=True
            io_name="in"
        else:
            io=False
            io_name="out"
        ttymidi=client.get_ports("ttymidi", is_output=io, is_midi=True)
        if(len(ttymidi)==0):
            if(io==True):
                hw=client.get_ports("system",is_midi=True, is_audio=False, is_output=True, is_physical=True)
            else:
                hw=client.get_ports("system",is_midi=True, is_audio=False, is_input=True, is_physical=True)
            if(len(hw)>0):
                if(unalias==True):
                    Logger.info("midi_alias:jack unalias %s => ttymidi:MIDI_%s" % (hw[0].name,io_name))
                    subprocess.call(JACKALIAS+" -u "+str(hw[0].name)+" ttymidi:MIDI_"+io_name,shell=True)
                else:
                    Logger.info("midi_alias:jack alias %s => ttymidi:MIDI_%s" % (hw[0].name,io_name))
                    subprocess.call(JACKALIAS+" "+str(hw[0].name)+" ttymidi:MIDI_"+io_name,shell=True)

def read_last_pedalboard():
    last_pedalboard_file=Path(LAST_PEDALBOARD_FILE)
    if(last_pedalboard_file.is_file()):
        f=open(LAST_PEDALBOARD_FILE,"r")
        if(f):
            last_pedalboard=f.readline()[:-1]
            Logger.info("read_last_pedalboard:last pedalboard: [%s]" % last_pedalboard)
            if(last_pedalboard==""):
                last_pedalboard="default"
                write_last_pedalboard(last_pedalboard)
            f.close()
        else:
            Logger.warning("Cannot read '%s'" % LAST_PEDALBOARD_FILE)
            last_pedalboard="default"
    else:
        write_last_pedalboard("default")
        last_pedalboard="default"
    return(last_pedalboard)

def write_last_pedalboard(pedalboard):
    global actual_pedalboard
    f=open(LAST_PEDALBOARD_FILE,"w")
    if(f):
        f.write(pedalboard+"\n")
        Logger.info("write_last_pedalboard: [%s]" % pedalboard)
        actual_pedalboard=pedalboard
        f.close()
    else:
        Logger.warning("Cannot create '%s'" % LAST_PEDALBOARD_FILE)

##############################################################################
# Main
##############################################################################

def main():
    global client,actual_pedalboard
    if(get_username()!='root'):
       Logger.critical("Program must run as root.")
       exit(100)

    startup_jack()
    
    client=jack.Client("stage")
    client.set_xrun_callback(xrun)
    midi_alias()

    mod_service("mod-host-pipe",True)
    actual_pedalboard=read_last_pedalboard()
    load_pedalboard(actual_pedalboard,init=True)
    Logger.info("main:loaded actual pedalboard: %s",actual_pedalboard)

    Logger.info("main:Start StageApp.")
    StageApp().run()
    Logger.info("main:StageApp ends.")
    quit_prog()

if(__name__=="__main__"):
    main()
    quit_prog()
