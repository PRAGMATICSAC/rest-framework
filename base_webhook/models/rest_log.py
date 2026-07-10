# -*- coding: utf-8 -*-
from odoo import models, fields, api


class RestLog(models.Model):
    _inherit = 'rest.log'
    _description = 'Log de Webhook REST'

    model = fields.Char(string='Modelo')
    record_id = fields.Integer(string='ID del registro')
    resource_ref = fields.Reference(selection='_referencable_models', string='Referencia al recurso')

    @api.model
    def _referencable_models(self):
        models = self.env['ir.model'].search([])
        return [(m.model, m.name) for m in models]