.PHONY: test run image
test:
	python -m unittest discover -s tests -v
run:
	python -m app.server
image:
	docker build -t devops-platform:local .
