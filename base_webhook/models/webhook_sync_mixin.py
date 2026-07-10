# -*- coding: utf-8 -*-
import json
import logging
import re
import traceback

import requests

from odoo import models, fields, api

_logger = logging.getLogger(__name__)



class WebhookSyncMixin(models.AbstractModel):
    _name = 'webhook.sync.mixin'
    _description = 'Mixin para sincronización de Webhooks'

    estado_verificacion = fields.Selection([
        ('no_enviado', 'No Enviado'),
        ('positivo', 'Sincronizado'),
        ('fallido', 'Fallido')
    ], string='Estado de Verificación', default='no_enviado')
    rest_log_ids = fields.One2many('rest.log', 'record_id', string='Logs de Webhook',
                                   domain=lambda self: [('model', '=', self._name)])
    rest_log_count = fields.Integer(string='Cantidad de Logs', compute='_compute_rest_log_count')

    def _compute_rest_log_count(self):
        for record in self:
            record.rest_log_count = self.env['rest.log'].search_count([
                ('model', '=', record._name),
                ('record_id', '=', record.id)
            ])

    def action_view_rest_logs(self):
        self.ensure_one()
        return {
            'name': 'Webhook Logs',
            'type': 'ir.actions.act_window',
            'res_model': 'rest.log',
            'view_mode': 'tree,form',
            'domain': [('model', '=', self._name), ('record_id', '=', self.id)],
            'context': {'default_model': self._name, 'default_record_id': self.id},
        }

    def action_force_sync(self):
        self.ensure_one()
        try:
            self.send_configured_webhook(operation='create')
            if self.estado_verificacion != 'positivo':
                self.send_configured_webhook(operation='write')
        except Exception as e_create:
            try:
                if self.estado_verificacion != 'positivo':
                    self.send_configured_webhook(operation='write')
            except Exception as e_write:
                _logger.error("Error en webhook write: %s", e_write)

    def _prepare_log_base(self, model_name, record_id, hook, payload, headers, resource_ref=False, bulk=False):

        hook_url = hook.url if bulk else self.render_url_from_record(hook.url)
        return {
            'model': model_name,
            'record_id': record_id,
            'request_method': hook.method,
            'request_url': hook_url,
            'params': json.dumps(payload),
            'headers': json.dumps(headers),
            'resource_ref': resource_ref,
        }

    def _log_success_or_failure(self, base_log_vals, response):
        result_log = {
            'result': response.text,
            'state': 'success' if response.status_code == 200 else 'failed'
        }
        if response.status_code != 200:
            try:
                result_log.update({
                    'error': str(response.status_code),
                    'exception_message': json.dumps(response.json(), ensure_ascii=False),
                })
            except Exception:
                result_log.update({
                    'error': str(response.status_code),
                    'exception_message': response.text,
                })
        return self.env['rest.log'].sudo().create({**base_log_vals, **result_log})

    def _log_exception(self, base_log_vals, exception):
        error_log = {
            'error': str(exception),
            'exception_name': type(exception).__name__,
            'exception_message': traceback.format_exc(),
            'state': 'failed',
        }
        return self.env['rest.log'].sudo().create({**base_log_vals, **error_log})

    def send_configured_webhook(self, operation, hook_method=None, values=None, alias=None):
        self.ensure_one()
        config_env = self.env['webhook.config'].sudo()
        model_name = self._name
        record_id = self.id

        domain = [('model_id.model', '=', model_name), ('active', '=', True), ('bulk_boolean', '=', False)]

        if operation == 'create':
            domain.append(('trigger_on_create', '=', True))
        elif operation == 'write':
            domain.append(('trigger_on_write', '=', True))
        if hook_method:
            domain.append(('method', '=', hook_method))
        if alias:
            domain.append(('alias', '=', alias))
        webhooks = config_env.search(domain)
        for hook in webhooks:
            headers = self.get_headers_for_request(hook)

            # Obtener body desde método personalizado del modelo
            if hook.body_method_name:
                body_method = getattr(self, hook.body_method_name, None)
                data = body_method() if callable(body_method) else (values or {})
            else:
                data = values or {}
            url = self.render_url_from_record(hook.url)
            base_log_vals = self._prepare_log_base(
                model_name=model_name,
                record_id=record_id,
                hook=hook,
                payload=data,
                headers=headers,
                resource_ref=f'{model_name},{record_id}',
                bulk=False
            )

            try:
                response = requests.request(
                    method=hook.method,
                    url=url,
                    json=data,
                    headers=headers,
                    timeout=10
                )
                self._log_success_or_failure(base_log_vals, response)
                if response.status_code == 200:
                    self.with_context(skip_webhook=True).write({'estado_verificacion': 'positivo'})
                else:
                    self.with_context(skip_webhook=True).write({'estado_verificacion': 'fallido'})

            except Exception as e:
                self._log_exception(base_log_vals, e)
                self.with_context(skip_webhook=True).write({'estado_verificacion': 'fallido'})

    def send_bulk_webhook(self, model_name, operation, records=None, values_list=None, alias=None):
        Config = self.env['webhook.config'].sudo()
        domain = [('model_id.model', '=', model_name), ('active', '=', True), ('bulk_boolean', '=', True)]

        if operation == 'create':
            domain.append(('trigger_on_create', '=', True))
        elif operation == 'write':
            domain.append(('trigger_on_write', '=', True))
        if alias:
            domain.append(('alias', '=', alias))

        webhooks = Config.search(domain)

        _logger.debug("Bulk webhook records: %s", records)
        for hook in webhooks:
            headers = self.get_headers_for_request(hook)
            body_method = getattr(self, hook.body_method_name, None)
            try:
                if records and callable(body_method):
                    data = body_method(records)
                elif callable(body_method):
                    data = body_method()
                else:
                    data = values_list or {}
            except Exception as e:
                data = values_list or {}

            base_log_vals = self._prepare_log_base(
                model_name=model_name,
                record_id=0,
                hook=hook,
                payload=data,
                headers=headers,
                resource_ref=False,
                bulk=True
            )
            try:
                response = requests.request(
                    method=hook.method,
                    url=hook.url,
                    json=data,
                    headers=headers,
                    timeout=10
                )
                self._log_success_or_failure(base_log_vals, response)

            except Exception as e:
                self._log_exception(base_log_vals, e)

    def render_url_from_record(self, url_template):
        """
        Reemplaza los placeholders {campo} en la URL con valores reales del registro.
        """
        self.ensure_one()
        placeholders = re.findall(r'{(.*?)}', url_template)
        for placeholder in placeholders:
            if hasattr(self, placeholder):
                value = getattr(self, placeholder)
                if value is None:
                    raise ValueError(f"El campo '{placeholder}' está vacío en el registro.")
                if isinstance(value, models.BaseModel):
                    # Campo Many2one (recordset único)
                    final_value = value.id
                else:
                    # Valor directo (int, str, etc.)
                    final_value = value
                url_template = url_template.replace(f'{{{placeholder}}}', str(final_value))
            else:
                raise ValueError(f"El campo '{placeholder}' no existe en el modelo {self._name}.")
        return url_template

    def get_headers_for_request(self, hook):
        return {'Content-Type': 'application/json'}
