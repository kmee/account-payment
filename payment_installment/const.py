# Copyright 2026 KMEE
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# Where each provider reports the installment data of a payment, as dotted paths
# in the notification data handed to `_process_notification_data`.
#
# The base module ships no mapping: a provider (or a glue module) declares its own
# by extending `payment.transaction._get_installment_notification_mapping`.
#
# Supported keys: installments, installment_amount, amount_charged,
# acquirer_reference, authorization_code, card_brand_code.
NOTIFICATION_MAPPING = {}
