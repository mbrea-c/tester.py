
test : aqmaps-0.0.1-SNAPSHOT.jar
	./tester.py

clean :
	rm -f readings-*.geojson
	rm -f flightpath-*.txt
	rm -f summary.text
	rm -f test-*.txt
