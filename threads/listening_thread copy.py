from constants import Constants
from threading import Thread, Event
from queue import Queue, Empty
import time
import os.path
import json
import sounddevice as sd
import soundfile as sf


class ListeningThread(Thread):
    # kwargs = {
    #   "output_directory"
    #  }
    def __init__(
        self,
        stop_event,
        finished_callback,
        group=None,
        target=None,
        name=None,
        args=(),
        kwargs=None,
    ):
        super(ListeningThread, self).__init__(
            group=group,
            target=target,
            name=name,
        )
        self.args = args
        self.kwargs = kwargs

        self.stop_event = stop_event
        self.listening_finished_callback = finished_callback
        self.conf_data = None

        self.output_directory = None
        self.rec_pos = 0
        self.rec_out_path = None
        self.__init_conf_data()

    def __init_conf_data(self):
        self.output_directory = self.kwargs["output_directory"]
        if not os.path.isdir(self.output_directory):
            raise Exception("output directory not found")

        self.conf_path = self.output_directory + os.path.sep + Constants.CONF_FILENAME
        if not os.path.isfile(self.conf_path):
            raise Exception("conf file not found")

        self.conf_data = json.load(open(self.conf_path))

        self.rec_pos = self.conf_data["rec_pos"]

        self.rec_out_path = (
            self.output_directory + os.path.sep + Constants.RECORDING_OUTPUT_FILENAME
        )

    def run(self):
        q = Queue(maxsize=Constants.BUFFERSIZE)
        event = Event()

        def callback(outdata, frames, time, status):
            assert frames == Constants.BLOCKSIZE
            if status.output_underflow:
                #print("Output underflow: increase blocksize?")
                raise sd.CallbackAbort
            assert not status
            try:
                data = q.get_nowait()
            except Empty as e:
                #print("Buffer is empty: increase buffersize?")
                raise sd.CallbackAbort from e
            if len(data) < len(outdata):
                outdata[: len(data)] = data
                outdata[len(data) :].fill(0)
                raise sd.CallbackStop
            else:
                outdata[:] = data

        

        with sf.SoundFile(
            self.rec_out_path,
            samplerate=Constants.SAMPLE_RATE,
            channels=Constants.CHANNELS,
            subtype=Constants.SUBTYPE,
        ) as f:
            read_pos = self.rec_pos
            f.seek(read_pos)
            for i in range(Constants.BUFFERSIZE):

                if f.tell() == f.frames and not read_pos == 0:
                    f.seek(0)

                if f.tell() == read_pos and not i == 0:
                    data = []
                    break
                else:
                    data = f.read(Constants.BLOCKSIZE)
                q.put_nowait(data)  # Pre-fill queue
            stream = sd.OutputStream(
                samplerate=f.samplerate,
                blocksize=Constants.BLOCKSIZE,
                channels=f.channels,
                callback=callback,
                finished_callback=event.set,
            )
            with stream:
                timeout = Constants.BLOCKSIZE * Constants.BUFFERSIZE / f.samplerate
                while len(data) and  not event.is_set() and not self.stop_event.is_set():

                    if f.tell() == f.frames and not read_pos == 0:
                        f.seek(0)

                    if f.tell() == read_pos:
                        data = []
                        break
                    else:
                        data = f.read(Constants.BLOCKSIZE)
                    
                    q.put(data, timeout=timeout)
                # Wait until playback is finished
                while not event.is_set() and not self.stop_event.is_set():
                    time.sleep(1)

                if event.is_set() and not self.stop_event.is_set():
                    self.listening_finished_callback()