
# This is used for reordering the Django Admin Panel

ADMIN_REORDER = (
    {
        'app': 'users', 
        'label': 'User Management', 
        'models': ('users.CustomUser',),
    },
    
    'teams',
    'deliverables',
    'sites',

    {
        'app': 'socialaccount',
        'label': 'Social Authentication',
        'models': (
            'socialaccount.SocialAccount',
            'socialaccount.SocialApp',
            'socialaccount.SocialToken',
        )
    },

)