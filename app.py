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

try:
    # Подключение к RabbitMQ
    print("Connecting to RabbitMQ...", flush=True)
    rabbitmq_connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_uri))
    rabbitmq_channel = rabbitmq_connection.channel()

    exchange_name = 'ResponseGeneratorDirectExchange'
    rabbitmq_channel.exchange_declare(exchange=exchange_name, exchange_type='direct')

    queue_name = 'response_generator_queue'
    rabbitmq_channel.queue_declare(queue=queue_name)
    rabbitmq_channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key='response-generator-key')

    # Подключение к MongoDB
    print("Connecting to MongoDB...", flush=True)
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client.get_database()
    chats_collection = db.get_collection('chats')

    print(chats_collection, flush=True)
    print("---------------------------------------------------------", flush=True )

    documents = chats_collection.find()

    # Вывод всех документов
    for document in documents:
        print(document, flush=True)



    print(' [*] Waiting for messages. To exit press CTRL+C', flush=True)

except Exception as e:
    print(f"Error during initialization: {str(e)}", flush=True)
    sys.exit(1)


# Функция для обработки сообщений из RabbitMQ
def callback(ch, method, properties, body):
    print(" Что-то пришло...  ", flush=True)

    try:
        # Получаем данные из сообщения
        data = json.loads(body.decode('utf-8'))
        user_chat_id = data['userChatId']
        message_text = data['messageText']

        document = chats_collection.find_one({'_id': user_chat_id})
        words = document.get('words', [])

        if document:
            # Новая строка для добавления в words
            new_word = {'role': 'user', 'content': message_text}  # Замените на необходимую строку

            # Добавление новой строки в words
            chats_collection.update_one(
                {'_id': user_chat_id},
                {'$push': {'words': new_word}}
            )
            words.append(new_word)

            # Проверка обновленного документа
            updated_document = chats_collection.find_one({'_id': user_chat_id})
            print(updated_document)


            # Генерируем ответ с помощью GPT-3.5
            client = Client()
            response = client.chat.completions.create(
                model=g4f.models.gpt_35_turbo,
                messages=words,
            )

            # Добавляем сгенерированный ответ в чат в MongoDB
            words.append({"role": "assistant", "content": response.choices[0].message.content})
            print(f"Generated response: {response.choices[0].message.content}", flush=True)

            chats_collection.update_one(
                {'_id': user_chat_id},
                {'$push': {'words': {"role": "assistant", "content": response.choices[0].message.content}}}
            )

            # Отправляем сгенерированный ответ на другой сервис через RabbitMQ
            rabbitmq_channel.basic_publish(
                exchange='myDirectExchange',
                routing_key='boss-key',
                body=json.dumps({'userChatId': user_chat_id, 'messageText': response.choices[0].message.content})
            )

        else:
            print(f'Документ с _id {user_chat_id} не найден.')

    except Exception as e:
        print(f"Error in callback function: {str(e)}", flush=True)




# Начинаем прослушивать очередь сообщений в RabbitMQ
try:

    rabbitmq_channel.basic_consume(queue='response_generator_queue', on_message_callback=callback, auto_ack=True)
    rabbitmq_channel.start_consuming()

except KeyboardInterrupt:
    print("Exiting...", flush=True)
    rabbitmq_channel.stop_consuming()

finally:
    rabbitmq_connection.close()
