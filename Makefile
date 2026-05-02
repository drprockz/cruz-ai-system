.PHONY: browser-live-tests
browser-live-tests:
	pytest -m live tests/services/test_browser_live.py -v
