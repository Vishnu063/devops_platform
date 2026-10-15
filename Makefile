.PHONY: install test run image demo
install:
	python -m pip install --only-binary=:all: --require-hashes -r requirements-dev.txt
test:
	coverage run -m unittest discover -s tests -v
	coverage xml
	coverage report --fail-under=85
run:
	gunicorn --config gunicorn.conf.py 'app.server:create_app()'
image:
	docker build --platform linux/amd64 -t devops-platform:local .

demo:
	python -m devops_toolkit demo
