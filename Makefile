.ONESHELL:

.PHONY: check
check: venv
	. venv/bin/activate
	type python3
	mypy FlaskSimpleAuth.py
	flake8 FlaskSimpleAuth.py
	pytest test.py

.PHONY: clean
clean:
	$(RM) -r venv __pycache__ *.egg-info dist build .mypy_cache .pytest_cache

.PHONY: install
install:
	pip3 install -e .

# for local testing
venv:
	python3 -m venv venv
	venv/bin/pip3 install wheel mypy flake8 pytest
	venv/bin/pip3 install flask bcrypt
	venv/bin/pip3 install -e .

# generate source and built distribution
dist:
	python3 setup.py sdist bdist_wheel

.PHONY: publish
publish: dist
	# provide pypi login/pw…
	twine upload dist/*
