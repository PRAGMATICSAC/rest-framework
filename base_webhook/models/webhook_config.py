# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WebhookConfig(models.Model):
    _name = 'webhook.config'
    _description = 'Configuración de Webhooks'

    name = fields.Char(string='Nombre')
    model_id = fields.Many2one('ir.model', string='Modelo')
    method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE')
    ], string='Método HTTP')
    url = fields.Char(string='URL del Webhook')
    active = fields.Boolean(string='Activo', default=True)
    trigger_on_create = fields.Boolean(string='Disparar en Crear')
    trigger_on_write = fields.Boolean(string='Disparar en Modificar')
    trigger_on_delete = fields.Boolean(string='Disparar en Eliminar')
    bulk_boolean = fields.Boolean(string='Bulk?')
    body_method_name = fields.Char(string='Método para generar el cuerpo')
    alias = fields.Char(string='Alias')
