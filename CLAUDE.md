# Claude Development Notes

## Running Django Management Commands

Always use the Docker environment to run Django management commands. Do NOT use the local virtual environment.

Use this pattern:
```bash
docker-compose exec web python manage.py <command>
```

Examples:
```bash
# Run shell
docker-compose exec web python manage.py shell

# Run migrations
docker-compose exec web python manage.py migrate

# Run tests
docker-compose exec web python manage.py test
```
