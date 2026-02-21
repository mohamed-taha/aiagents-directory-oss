from django import forms
from aiagents_directory.agents.models import AgentSubmission


class AgentSubmissionForm(forms.ModelForm):
    """Form for submitting a new agent to the directory."""
    
    class Meta:
        model = AgentSubmission
        fields = ['email', 'agent_name', 'agent_website', 'agent_description']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-500 focus:border-transparent',
                'placeholder': 'your@email.com',
            }),
            'agent_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-500 focus:border-transparent',
                'placeholder': 'Example: Cursor',
            }),
            'agent_website': forms.URLInput(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-500 focus:border-transparent',
                'placeholder': 'Example: https://www.cursor.com',
            }),
            'agent_description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-accent-500 dark:focus:ring-accent-500 focus:border-transparent',
                'placeholder': 'Example: Fast, intelligent, and private, Cursor is the best way to code with AI.',
                'rows': 5,
            }),
        }
        labels = {
            'email': 'Your Email',
            'agent_name': 'What is the name of the agent?',
            'agent_website': 'What is the website of the agent?',
            'agent_description': 'Please provide a brief description of the agent',
        }
        help_texts = {
            'email': "We'll use this to send you updates about your agent's status and exclusive opportunities.",
            'agent_name': '',
            'agent_website': '',
            'agent_description': '',
        }

