import asyncio
import json
import sys

import g4f.models
import pika
from bson import ObjectId
from g4f.client import Client

from pymongo import MongoClient


# Строка подключения к RabbitMQ
rabbitmq_uri = "amqp://guest:guest@home-rabbitmq-1:5672/"

# Строка подключения к MongoDB
mongo_uri = "mongodb://mongodb:27017/chat_database"

# Создаем объекты для подключения
rabbitmq_connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_uri))
rabbitmq_channel = rabbitmq_connection.channel()

exchange_name = 'ResponseGeneratorDirectExchange'
rabbitmq_channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
queue_name = 'response_generator_queue'
rabbitmq_channel.queue_declare(queue=queue_name)

# Привязываем очередь к обменнику с указанием ключа маршрутизации (routing key)
routing_key = 'response-generator-key'
rabbitmq_channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=routing_key)

mongo_client = MongoClient(mongo_uri)
db = mongo_client.get_database()
chats_collection = db.get_collection('chats')


# Функция для обработки сообщений из RabbitMQ
def callback(ch, method, properties, body):
    # Получаем данные из сообщения
    data = json.loads(body.decode('utf-8'))
    user_chat_id = data['userChatId']
    message_text = data['messageText']

    # Находим соответствующий чат в MongoDB
    chat_data = chats_collection.find_one({'_id': ObjectId(user_chat_id)})
    if chat_data:
        # Достаем все сообщения из чата
        previous_messages = chat_data.get('words', [])

        previous_messages.append({"role": "user", "content": message_text})

        client = Client()
        response = client.chat.completions.create(
            model=g4f.models.gpt_35_turbo,
            messages=previous_messages,

        )
        previous_messages.append({"role": "assistant", "content": response.choices[0].message.content})
        print(response.choices[0].message.content)

        # Добавляем сгенерированный ответ в чат в MongoDB
        chats_collection.update_one(
            {'_id': ObjectId(user_chat_id)},
            {'$push': {'words': previous_messages}}
        )

        # Отправляем сгенерированный ответ на другой сервис через RabbitMQ
        rabbitmq_channel.basic_publish(
            exchange='myDirectExchange',
            routing_key='boss-key',  # Название очереди для сгенерированных ответов
            body=json.dumps({'userChatId': user_chat_id, 'generatedResponse': response.choices[0].message.content})
        )

    else:
        print(f"Chat with id {user_chat_id} not found in MongoDB")


# Начинаем прослушивать очередь сообщений в RabbitMQ
rabbitmq_channel.queue_declare(queue='user_messages_queue', durable=True)
rabbitmq_channel.basic_consume(queue='user_messages_queue', on_message_callback=callback, auto_ack=True)

print(' [*] Waiting for messages. To exit press CTRL+C')

# Запускаем бесконечный цикл ожидания сообщений из RabbitMQ
rabbitmq_channel.start_consuming()

