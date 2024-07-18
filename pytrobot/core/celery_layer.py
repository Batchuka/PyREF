from celery import Celery, Task
import boto3
from datetime import datetime

class CeleryManager:
    """
    This manager uses SQS as queue. Obligatory uses CLI credentials to assume role for URL queue passed.
    """
    def __init__(self, region_name, role_arn, queue_url, queue_name, visibility_timeout=3600, polling_interval=10):
        self.region_name = region_name
        self.role_arn = role_arn
        self.queue_url = queue_url
        self.queue_name = queue_name
        self.visibility_timeout = visibility_timeout
        self.polling_interval = polling_interval

        # Obter credenciais da AWS CLI
        session = boto3.Session()
        credentials = session.get_credentials()
        aws_access_key_id = credentials.access_key
        aws_secret_access_key = credentials.secret_key

        self.broker_url = f'sqs://{aws_access_key_id}:{aws_secret_access_key}@'
        self.celery_app = Celery('tasks', broker=self.broker_url)
        self.celery_app.conf.update(
            broker_transport_options={
                'region': self.region_name,
                'visibility_timeout': self.visibility_timeout,
                'polling_interval': self.polling_interval,
                'predefined_queues': {
                    self.queue_name: {
                        'url': self.queue_url
                    }
                }
            },
            broker_connection_retry_on_startup=True,
            task_acks_late=True
        )


        self.celery_app.conf.task_default_queue = self.queue_name
        self.sqs_client = self._assume_role_and_get_sqs_client()

    def _assume_role_and_get_sqs_client(self):
        sts_client = boto3.client('sts')
        session_name = f"AssumeRoleSession_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        assumed_role_object = sts_client.assume_role(
            RoleArn=self.role_arn,
            RoleSessionName=session_name,
            DurationSeconds=self.visibility_timeout
        )
        credentials = assumed_role_object['Credentials']
        sqs_client = boto3.client(
            'sqs',
            region_name=self.region_name,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
        )
        return sqs_client
    
    def purge_queue(self):
        #TODO : é preciso permissão para fazer isso.
        self.sqs_client.purge_queue(QueueUrl=self.queue_url)

    def Worker(self, cls):
        task_name = f'{cls.__module__}.{cls.__name__}.run'
        task = self.celery_app.task(name=task_name, base=BaseWorker)(cls().run)
        return task

    def run(self):
        # self.purge_queue()
        self.celery_app.start(argv=['worker', '--loglevel=info'])

class BaseWorker(Task):
    abstract = True

    def run(self, *args, **kwargs):
        raise NotImplementedError("O método 'run' deve ser implementado pelo worker.")


