.PHONY: docker/build docker/run

docker/build:
	docker build -t sales-parser .

docker/run:
	docker run --rm --name sales-parser-cnt sales-parser

test:
	poetry run pytest

rebuild:
	rm dist/*
	poetry build

upload:
	twine upload dist/*

