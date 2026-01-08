import os
import cv2
import base64
import sqlite3
import uuid
from utils.screen_shot import VideoScreenshot


def _create_repo(repo_file):
    conn = sqlite3.connect(repo_file)
    cursor = conn.cursor()
    cursor.execute(
        """create table if not exists videos(
            uuid varchar(64) primary key,
            path varchar(1024) unique not null,
            score int default 0
            )
        """
    )
    cursor.close()
    conn.commit()
    conn.close()


def _decode_path(path):
    return base64.b64decode(path.encode()).decode('utf-8')


def _encode_path(path):
    return base64.b64encode(path.encode('utf-8')).decode()


def _tuple_to_dict(value):
    if value is None or len(value) == 0:
        return None
    return {
        'uuid': value[0],
        'path': _decode_path(value[1]),
        'score': value[2]
    }


class Repository:
    def __init__(self, repo_file):
        if not os.path.exists(repo_file):
            _create_repo(repo_file)
        self.conn = sqlite3.connect(repo_file)

    def find_by_uuid(self, uid):
        cursor = self.conn.cursor()
        cursor.execute('select * from videos where uuid=?', (uid,))
        value = cursor.fetchone()
        cursor.close()
        return _tuple_to_dict(value)

    def find_by_path(self, path):
        cursor = self.conn.cursor()
        path = _encode_path(path)
        cursor.execute('select * from videos where path=?', (path,))
        value = cursor.fetchone()
        cursor.close()
        return _tuple_to_dict(value)

    def find_all(self):
        cursor = self.conn.cursor()
        cursor.execute('select * from videos')
        values = cursor.fetchall()
        return [_tuple_to_dict(value) for value in values]

    def find_with_score(self, lower=1, upper=100):
        cursor = self.conn.cursor()
        cursor.execute('select * from videos where score >= ? and score <= ? order by score desc', (lower, upper))
        values = cursor.fetchall()
        return [_tuple_to_dict(value) for value in values]

    def insert(self, uid, path):
        cursor = self.conn.cursor()
        path = _encode_path(path)
        cursor.execute('insert into videos(uuid, path) values (?, ?)', (uid, path))
        cursor.close()
        self.conn.commit()

    def update_score(self, uid, score):
        cursor = self.conn.cursor()
        cursor.execute('update videos set score=? where uuid=?', (score, uid))
        cursor.close()
        self.conn.commit()

    def update_path(self, uid, path):
        cursor = self.conn.cursor()
        path = _encode_path(path)
        cursor.execute('update videos set path=? where uuid=?', (path, uid))
        cursor.close()
        self.conn.commit()

    def delete(self, uid):
        self.conn.execute('delete from videos where uuid=?', (uid,))
        self.conn.commit()

    def __del__(self):
        self.conn.close()


cache_dir = 'cache'
cache_repo = 'cache.db'

small_frame_size = (240, 160)
frame_size = (960, 480)


class VideoFile:
    def __init__(self, path):
        self.path = path
        self.uid = None
        self.score = 0
        repo = Repository(cache_repo)
        if path is not None:
            rcd = repo.find_by_path(path)
            if rcd is None:
                self.uid = str(uuid.uuid4())
                repo.insert(self.uid, path)
            else:
                self.uid = rcd['uuid']
                self.score = rcd['score']
        else:
            raise Exception('invalid arguments')
        self.screenshot = None
        self.small_frames = []
        self.cur_cv_frame = None
        self.cur_frame = None

    def _init_screen_shot(self):
        if self.screenshot is None:
            self.screenshot = VideoScreenshot(self.path)

    def grab_frame(self, pos=None):
        self._init_screen_shot()
        size = frame_size
        if pos and pos > 0:
            frame = self.screenshot.grab(percent=pos, resize=size)
        else:
            frame = self.screenshot.grab(resize=size)
        if frame is not None:
            self.cur_cv_frame = frame
            self.cur_frame = cv2.imencode('.png', frame)[1].tobytes()
        return self.cur_frame

    def get_cur_frame(self):
        return self.cur_frame

    def get_cur_cv_frame(self):
        return self.cur_cv_frame

    def grab_small_frames(self):
        self._init_screen_shot()
        self.small_frames.clear()
        size = small_frame_size
        for i in range(1, 13):
            frame = self.screenshot.grab(8 * i, size)
            if frame is None:
                break
            img_bytes = cv2.imencode('.png', frame)[1].tobytes()
            self.small_frames.append(img_bytes)
        return self.small_frames

    def get_small_frames(self):
        return self.small_frames

    def is_cache_exist(self):
        return os.path.exists(self._cache_file())

    def is_file_exist(self):
        return os.path.exists(self.path)

    def _cache_file(self):
        return os.path.join(cache_dir, self.uid)

    def load_cache(self):
        cache_file = os.path.join(cache_dir, self.uid)
        if not os.path.exists(cache_file):
            return False
        self.small_frames.clear()
        with open(cache_file, mode='rb') as file:
            while True:
                buff = file.read(2)
                magic = int.from_bytes(buff, 'little')
                if magic == 0xffff:
                    # print('reach cache file end')
                    return True
                if magic != 0xacbc:
                    print('error cache file')
                    return False
                buff = file.read(4)
                length = int.from_bytes(buff, 'little')
                self.small_frames.append(file.read(length))

    def save_cache(self):
        if not os.path.isdir(cache_dir):
            os.mkdir(cache_dir)
        with open(os.path.join(cache_dir, self.uid), mode='wb') as file:
            for frame in self.small_frames:
                file.write(0xacbc.to_bytes(length=2, byteorder='little'))
                file.write(len(frame).to_bytes(length=4, byteorder='little'))
                file.write(frame)
            file.write(0xffff.to_bytes(length=2, byteorder='little'))

    def delete_cache(self):
        Repository(cache_repo).delete(self.uid)
        if self.is_cache_exist():
            os.remove(self._cache_file())

    def set_score(self, score):
        self.score = score
        repo = Repository(cache_repo)
        repo.update_score(self.uid, score)

    def get_score(self):
        return self.score

    def modify_path(self, path):
        self.path = path
        repo = Repository(cache_repo)
        repo.update_path(self.uid, path)

