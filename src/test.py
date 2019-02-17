#coding:utf-8
import copy
import json
import hashlib
import sqlite3
from datetime import datetime

import web
from socketio import socketio_manage
from socketio.namespace import BaseNamespace
from socketio.mixins import RoomsMixin, BroadcastMixin

from models import Message, User, Topic

session = web.config._session

CACHE_USER = {}
render = web.template.render('templates/')



def sha1(data):
    return hashlib.sha1(data).hexdigest()


def bad_request(message):
    raise web.BadRequest(message=message)

class CJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        else:
            return json.JSONEncoder.default(self, obj)

def to_json(data):
    return json.dumps(data, cls=CJsonEncoder)

class Test(object):
    def GET(self):
        return render.test()

class MessageHandler:
    def GET(self):
        topic_id = web.input().get('topic_id')
        if topic_id:
            messages = Message.get_by_topic(topic_id) or []
        else:
            messages = Message.get_all()

        result = []
        current_user_id = session.user.id
        for m in messages:
            try:
                user = CACHE_USER[m.user_id]
            except KeyError:
                user = User.get_by_id(m.user_id)
                CACHE_USER[m.user_id] = user
            message = dict(m)
            message['user_name'] = user.username
            message['is_mine'] = (current_user_id == user.id)
            result.append(message)
        return to_json(result)

    def POST(self):
        data = web.data()
        data = json.loads(data)
        if not (session.user and session.user.id):
            return bad_request("请先登录！")

        message_data = {
            "content": data.get("content"),
            "topic_id": data.get("topic_id"),
            "user_id": session.user.id,
            "created_time": datetime.now(),
        }
        m_id = Message.create(**message_data)
        result = {
            "id": m_id,
            "content": message_data.get("content"),
            "topic_id": message_data.get("topic_id"),
            "user_id": session.user.id,
            "user_name": session.user.username,
            "created_time": str(message_data.get("created_time")),
            "is_mine": True,
        }
        return to_json(result)


class ChatNamespace(BaseNamespace, RoomsMixin, BroadcastMixin):
    def on_go_out(self):
        room_num = self.socket.session.get('room')
        if room_num:
            print 'go_out', room_num
            self.leave(room_num)

    def on_topic(self, topic_id):
        """ 加入以某个主题id为房间

        客户端进入聊天室界面先发送此请求，确定房间号
        """
        room_num = 'room_%s' % topic_id
        self.socket.session['room'] = room_num
        print 'join', room_num
        self.join(room_num)

    def on_message(self, model):
        user = self.environ['user']
        if user is None:
            # 手动从store中取出user
            session_id = self.environ['session_id']
            _data = session.store[session_id]
            user = _data['user']
        model.update({
            "user_id": user.id,
            "created_time": datetime.now(),
        })
        m_id = Message.create(**model)
        model.update({
            "user_name": user.username,
            'id': m_id,
            'created_time': str(model['created_time']),
            'is_mine': True,
        })
        # 发送回客户端
        self.emit('message', model)

        # 发送给其他人
        model['is_mine'] = False
        self.emit_to_room(
            self.socket.session['room'],
            'message',
            model,
        )

    def recv_disconnect(self):
        print 'DISCONNECT!!!!!!!!!!!!!!!!!!!!!!!'
        self.disconnect(silent=True)


class SocketHandler:
    def GET(self):
        context = copy.copy(web.ctx.environ)
        context.update({
            "user": session.user,
            "session_id": session.session_id,
        })
        socketio_manage(context, {'': ChatNamespace})
        # 重新载入session数据，因为session在socket请求中改变了
        session._load()
