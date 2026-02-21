from django.db import models


class AgentStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    PUBLISHED = 'PUBLISHED', 'Published'
    ARCHIVED = 'ARCHIVED', 'Archived'


class PricingModel(models.TextChoices):
    UNKNOWN = 'UNKNOWN', 'Unknown'
    FREE = 'FREE', 'Free'
    FREEMIUM = 'FREEMIUM', 'Freemium'
    PAID = 'PAID', 'Paid'
    ENTERPRISE = 'ENTERPRISE', 'Enterprise'
    CONTACT = 'CONTACT', 'Contact for Pricing'

class Industry(models.TextChoices):
    UNKNOWN = 'UNKNOWN', 'Unknown'
    GENERAL = 'GENERAL', 'General Purpose'
    HEALTHCARE = 'HEALTHCARE', 'Healthcare'
    FINANCE = 'FINANCE', 'Finance'
    EDUCATION = 'EDUCATION', 'Education'
    ECOMMERCE = 'ECOMMERCE', 'E-commerce'
    MARKETING = 'MARKETING', 'Marketing'
    LEGAL = 'LEGAL', 'Legal'
    HR = 'HR', 'Human Resources'
    TECH = 'TECH', 'Technology'
    CUSTOMER_SERVICE = 'CUSTOMER_SERVICE', 'Customer Service'
    RESEARCH = 'RESEARCH', 'Research'
    CONTENT = 'CONTENT', 'Content Creation'