import threading
import queue
import PySimpleGUI as sg
from utils.face_detect import FaceDetect
from video_file import *


class MediaFinder:
    def __init__(self, folder, suffixes=None):
        if suffixes is None:
            suffixes = ['.mp4',
                        '.avi',
                        '.wmv',
                        '.rmvb',
                        '.mkv',
                        '.TS',
                        '.ts'
                        ]
        self.root = folder
        self.suffixes = suffixes
        self.files = []

    def find_all(self):
        for root, dirs, files in os.walk(self.root):

            for file in files:
                for suffix in self.suffixes:
                    if file.endswith(suffix):
                        path = os.path.join(root, file)
                        path = path.replace('/', '\\')
                        self.files.append(path)
        return self.files


class VideoProcess(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self, name='video_process')
        self._que = queue.Queue()
        self._is_stopped = False

    def run(self):
        while not self._is_stopped:
            msg = self._que.get(True)
            if msg is None:
                print('process thread quit')
                break
            path = msg['path']
            print('process ' + path)
            video = VideoFile(path=path)
            if (not video.is_cache_exist()) and (video.get_score() >= 0):
                video.grab_small_frames()
                video.save_cache()

    def process(self, path):
        self._que.put({
            'path': path
        })

    def stop(self):
        self._que.put(None)
        self._is_stopped = True
        self.join()


_video_processor = VideoProcess()


class ScoreMarkWindow:
    def __init__(self, score=0):
        layout = [[sg.Text('Give a mark for current video <0-100>')],
                  [sg.InputText(default_text=str(score), size=(20, 1), do_not_clear=False, key='_INPUT_'),
                   sg.Button('Ok', size=(5, 1), bind_return_key=True)]
                  ]
        self.window = sg.Window(title='Mark', layout=layout, keep_on_top=True)

    def read(self):
        while True:
            button, values = self.window.Read()
            if button != 'Ok':
                return None
            value = values['_INPUT_']
            if not value.isdecimal():
                sg.popup_error('invalid score', keep_on_top=True)
            else:
                break
        return int(value)

    def __del__(self):
        self.window.close()
        del self.window


class DirectoryChangeWindow:
    def __init__(self):
        layout = [[sg.Text('Original Folder:'),
                   sg.InputText(size=(20, 1), do_not_clear=False, key='_SRC_')],
                  [sg.Text('Modified Folder:'),
                   sg.InputText(size=(20, 1), do_not_clear=False, key='_DST_')],
                  [sg.Text(size=(15, 1)), sg.Button('Cancel', size=(5, 1)),
                   sg.Button('Ok', size=(5, 1), bind_return_key=True)]
                  ]
        self.window = sg.Window(title='Mark', layout=layout, keep_on_top=True)

    def read(self):
        src = ''
        dst = ''
        while True:
            button, values = self.window.Read()
            if button != 'Ok':
                break
            src = values['_SRC_']
            dst = values['_DST_']
            src = src.strip()
            dst = dst.strip()
            if len(src) is 0 or len(dst) is 0:
                break
            if not src.endswith('\\') and not src.endswith('/'):
                src = src + '\\'
            if not dst.endswith('\\') and not dst.endswith('/'):
                dst = dst + '\\'
        return src, dst

    def __del__(self):
        self.window.close()
        del self.window


class SelectByScoreWindow:
    def __init__(self):
        layout = [[sg.Text('score range')],
                  [sg.InputText(default_text='60', size=(10, 1), key='_lower_'),
                   sg.Text('-'),
                   sg.InputText(default_text='100', size=(10, 1), key='_upper_'),
                   sg.Button('Ok', size=(5, 1), bind_return_key=True)]
                  ]
        self.window = sg.Window(title='Select', layout=layout, keep_on_top=True)

    def read(self):
        while True:
            button, values = self.window.Read()
            if button != 'Ok':
                return None, None
            lower = values['_lower_']
            upper = values['_upper_']
            if not lower.isdecimal() or not upper.isdecimal():
                sg.popup_error('invalid score', keep_on_top=True)
            else:
                break
        return int(lower), int(upper)

    def __del__(self):
        self.window.close()
        del self.window


class VideoPlayer:
    def __init__(self):
        graph_col = [
            [sg.Graph((960, 500), (0, 0), (960, 500), background_color='black', key='graph', pad=(0, 0))],
            [sg.Slider((1, 100), size=(110, 20), pad=(0, 0), orientation='h', disable_number_display=True,
                       enable_events=True, key='slider'), sg.Button('Play', size=(8, 1))]
        ]
        files_col = [
            [sg.Listbox(values=[], size=(30, 30), enable_events=True, select_mode=sg.LISTBOX_SELECT_MODE_EXTENDED,
                        key='listbox', pad=(0, 0))],
            [sg.Text('Total:', pad=(0, 0)), sg.Text('0', size=(10, 1), key='total_count', pad=(0, 0))]
        ]
        layout = [
            [
                sg.Menu([
                    ['&File', ['Open Folder', 'Close all']],
                    ['&Edit', ['&Detect face', '&Mark', 'Open container folder',
                               'List not exists', 'List same names', 'List key words',
                               '&Remove selected', 'Modify selected directory']
                     ],
                    ['&History', ['All::load_all', 'Marked::load_marked']],
                    ['&Settings', ['Face detect']]
                ])
            ],
            [
                sg.Column(files_col, pad=(0, 0)),
                sg.Column(graph_col)
            ]
        ]
        self.window = sg.Window('Video Player', layout, return_keyboard_events=True,
                                use_default_focus=False, resizable=False)
        self.graph = self.window['graph']
        self.event_dispatch = {
            'Open Folder': self._handle_open_folder,
            'Open container folder': self._handle_open_container_folder,
            'Close all': self._handle_close_all,
            'All::load_all': self._handle_load_all,
            'Marked::load_marked': self._handle_load_marked,
            'Mark': self._handle_mark,
            'listbox': self._handle_file_selected,
            'Play': self._handle_play_video,
            'Detect face': self._handle_detect_face,
            'Remove selected': self._handle_file_remove,
            'Modify selected directory': self._handle_modify_directory,
            'List not exists': self._handle_list_not_exists,
            'List same names': self._handle_list_same_names,
            'List key words': self._handle_list_key_words,
            'slider': self._handle_slider_move
        }
        self.selected_video = None

    def run(self):
        while True:
            event, values = self.window.read()
            # print(event, values)
            if event is None:
                break
            elif event in self.event_dispatch:
                if event in values:
                    self.event_dispatch[event](values[event])
                else:
                    self.event_dispatch[event]()

        self.window.close()

    def _handle_open_folder(self):
        items = self.window['listbox'].GetListValues()
        folder = sg.popup_get_folder('Folder to open', default_path='')
        if folder:
            files = MediaFinder(folder).find_all()
            for file in files:
                if file not in items:
                    items.append(file)
                    _video_processor.process(file)
        self._update_file_list(items)

    def _handle_open_container_folder(self):
        if self.selected_video is not None:
            path = self.selected_video.path
            path = os.path.dirname(path)
            if not os.path.isdir(path):
                sg.popup_error('file not exists', keep_on_top=True)
                return
            os.startfile(path)

    def _handle_list_not_exists(self):
        listbox = self.window['listbox']
        files = listbox.GetListValues()
        not_exists = []
        for file in files:
            if not os.path.exists(file):
                not_exists.append(file)
        self._update_file_list(not_exists)

    def _handle_list_same_names(self):
        listbox = self.window['listbox']
        files = listbox.GetListValues()
        names = dict()
        for file in files:
            name = os.path.basename(file)
            if name in names:
                names[name].append(file)
            else:
                names[name] = [file]
        files_with_same_name = []
        for _, paths in names.items():
            if len(paths) > 1:
                files_with_same_name += paths
        self._update_file_list(files_with_same_name)

    def _handle_list_key_words(self):
        words = sg.PopupGetText('Input the key words', title='Input', keep_on_top=True)
        if words is None or len(words) == 0:
            return
        print('select file paths contains key words: %s' % words)
        listbox = self.window['listbox']
        files = listbox.GetListValues()
        results = []
        for file in files:
            if words in file:
                results.append(file)
        self._update_file_list(results)

    def _handle_close_all(self):
        self.window['slider'].Update(1)
        self.window['graph'].Erase()
        self.selected_video = None
        self._update_file_list([])

    def _handle_load_all(self):
        repo = Repository(cache_repo)
        files = repo.find_all()
        self._update_file_list([file['path'] for file in files])

    def _handle_load_marked(self):
        lower, upper = SelectByScoreWindow().read()
        repo = Repository(cache_repo)
        files = repo.find_with_score(lower, upper)
        self._update_file_list([file['path'] for file in files])

    def _handle_mark(self):
        if self.selected_video is not None:
            score = ScoreMarkWindow(self.selected_video.score).read()
            if score is not None:
                self.selected_video.set_score(score)

    def _handle_file_remove(self):
        listbox = self.window['listbox']
        files = listbox.GetListValues()
        selected = listbox.get()
        for file in selected:
            VideoFile(file).delete_cache()
            files.remove(file)
        self._update_file_list(files)

    def _update_file_list(self, files):
        self.window['listbox'].Update(files)
        self.window['total_count'].Update(str(len(files)))

    def _handle_file_selected(self, files):
        if len(files) is 0:
            return
        path = files[0]
        if self.selected_video is None or self.selected_video.path is not path:
            self.selected_video = VideoFile(path)
            if self.selected_video.is_cache_exist():
                self.selected_video.load_cache()
        self._display_small_graphs()

    def _handle_modify_directory(self):
        src, dst = DirectoryChangeWindow().read()
        if len(src) is 0 or len(dst) is 0:
            return
        print('change directory from %s to %s for selected files' % (src, dst))
        listbox = self.window['listbox']
        files = listbox.GetListValues()
        selected = listbox.get()
        for file in selected:
            if file.startswith(src):
                i = files.index(file)
                new_file = file.replace(src, dst, 1)
                print('change file %d from %s to %s' % (i, file, new_file))
                files[i] = new_file
                VideoFile(file).modify_path(new_file)
        self._update_file_list(files)
        return

    def _handle_play_video(self):
        if self.selected_video is None or not self.selected_video.is_file_exist():
            sg.popup_error('file not exists', keep_on_top=True)
            return
        os.startfile(self.selected_video.path)

    def _display_video(self, pos=None):
        if self.selected_video is None or not self.selected_video.is_file_exist():
            sg.popup_error('file not exists', keep_on_top=True)
            return
        self.graph.Erase()
        frame = self.selected_video.grab_frame(pos)
        if frame is not None:
            self.graph.DrawImage(data=frame, location=(0, 480))
        self.graph.DrawText(self.selected_video.path, location=(0, 500), color='white',
                            text_location=sg.TEXT_LOCATION_TOP_LEFT)

    def _display_small_graphs(self):
        if self.selected_video is None:
            return
        frames = self.selected_video.get_small_frames()
        self.graph.Erase()
        size = small_frame_size
        for j in range(0, 3):
            for i in range(0, 4):
                index = j * 4 + i
                if index >= len(frames):
                    break
                frame = frames[index]
                if frame is not None:
                    width = size[0]
                    height = size[1]
                    self.graph.DrawImage(data=frame,  location=(i * width + 10, 480 - j * (height + 10)))

        self.graph.DrawText(self.selected_video.path, location=(0, 500), color='white',
                            text_location=sg.TEXT_LOCATION_TOP_LEFT)

    def _handle_slider_move(self, pos):
        self._display_video(pos)

    def _handle_detect_face(self):
        if self.selected_video is None or self.selected_video.get_cur_cv_frame() is None:
            return
        frame = self.selected_video.get_cur_cv_frame()
        fd = FaceDetect()
        num = fd.detect(frame)
        if num > 0:
            img_bytes = cv2.imencode('.png', frame)[1].tobytes()
            self.graph.DrawImage(data=img_bytes, location=(10, 480))


if __name__ == '__main__':
    os.chdir("../workdir/")  
    _video_processor.start()
    VideoPlayer().run()
    _video_processor.stop()
