############################################
#
# Author: Luca Cinquini
#
############################################
"""
Client-side API for invoking WPS services.

"""

from etree import etree
from owslib.ows import DEFAULT_OWS_NAMESPACE, XSI_NAMESPACE, XLINK_NAMESPACE, \
    OWS_NAMESPACE_1_0_0, ServiceIdentification, ServiceProvider, OperationsMetadata
from time import sleep
from wps_utils import build_get_url, dump, getTypedValue, parseText
from xml.dom.minidom import parseString
import util

# the following namespaces should be inserted in ows.py
WPS_NAMESPACE="http://www.opengis.net/wps/1.0.0"
WPS_SCHEMA_LOCATION = 'http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd'
WPS_DEFAULT_VERSION = '1.0.0'

WFS_NAMESPACE = 'http://www.opengis.net/wfs'
OGC_NAMESPACE = 'http://www.opengis.net/ogc'

GML_NAMESPACE = 'http://www.opengis.net/gml'
GML_SCHEMA_LOCATION = "http://schemas.opengis.net/gml/3.1.1/base/feature.xsd"

DRAW_NAMESPACE = 'gov.usgs.cida.gdp.draw'
DRAW_SCHEMA_LOCATION = 'http://cida.usgs.gov/qa/climate/derivative/xsd/draw.xsd'



# list of namespaces used by this module
namespaces = {
    None : WPS_NAMESPACE,
    'wps': WPS_NAMESPACE,
    'ows': DEFAULT_OWS_NAMESPACE,
    'xlink': XLINK_NAMESPACE,
    'xsi': XSI_NAMESPACE,
    'wfs': WFS_NAMESPACE,
    'ogc': OGC_NAMESPACE,
    'gml': GML_NAMESPACE,
}

#class IWebProcessingService(IService):
#    """
#    Abstract interface for an OGC Web Processing Service (WPS).
#    """
    
#    def getcapabilities(self, **kw):
#        """
#        Makes a GetCapabilities request to the remote WPS server,
#        returns an XML document wrapped in a python file-like object.
#        """

class WebProcessingService(object):
    """
    Class that contains client-side functionality for invoking an OGC Web Processing Service (WPS).
    
    Implements IWebProcessingService.
    """
    
    def __init__(self, url, version=WPS_DEFAULT_VERSION, username=None, password=None, verbose=False):
        """
        Initialization method resets the object status, it does NOT execute a GetCapabilities invocation to the remote service.
        """
        
        # fields passed in from object initializer
        self.url = url
        self.username = username
        self.password = password
        self.version = version
        self.verbose = verbose
                
        # fields populated by method invocations
        self._capabilities = None
        self.identification = None
        self.provider = None
        self.operations=[]
        self.processes=[]
        
    def getcapabilities(self, xml=None):
        """
        Method that requests a capabilities document from the remote WPS server and populates this object's metadata.
        keyword argument xml: local XML GetCapabilities document, prevents actual HTTP invocation.
        """
        
        # read capabilities document
        reader = WPSCapabilitiesReader(version=self.version, verbose=self.verbose)
        if xml:
            # read from stored XML file
            self._capabilities = reader.readFromString(xml)
        else:
            self._capabilities = reader.readFromUrl(self.url, username=self.username, password=self.password)
            
        if self.verbose==True:
            print util.xml2string(etree.tostring(self._capabilities))

        # populate the capabilities metadata obects from the XML tree
        self._parseCapabilitiesMetadata(self._capabilities)
        
    def describeprocess(self, identifier, xml=None):
        """
        Requests a process document from a WPS service and populates the process metadata.
        Returns the process object.
        """
        
        # read capabilities document
        reader = WPSDescribeProcessReader(version=self.version, verbose=self.verbose)
        if xml:
            # read from stored XML file
            process = reader.readFromString(xml)
        else:
            # read from server
            process = reader.readFromUrl(self.url, identifier)
            
        if self.verbose==True:
            print util.xml2string(etree.tostring(process))
            #print parseString(etree.tostring(process)).toprettyxml()

        # build metadata objects
        return self._parseProcessMetadata(process)
        
    def execute(self, identifier, inputs, output=None, request=None, response=None):
        """
        Submits a WPS process execution request. 
        Returns a WPSExecution object, which can be used to monitor the status of the job, and ultimately retrieve the result.
        
        identifier: the requested process identifier
        inputs: list of process inputs as (key, value) tuples (where value is either a string for LiteralData, or an object for ComplexData)
        output: optional identifier for process output reference (if not provided, output will be embedded in the response)
        request: optional pre-built XML request document, prevents building of request from other arguments
        response: optional pre-built XML response document, prevents submission of request to live WPS server
        """
        
        # instantiate a WPSExecution object
        print 'Executing WPS request...'
        execution = WPSExecution(version=self.version, url=self.url, username=self.username, password=self.password, verbose=self.verbose)

        # build XML request from parameters 
        if request is None:
           requestElement = execution.buildRequest(identifier, inputs, output)
           request = etree.tostring( requestElement )   
        if self.verbose==True:
               print request
        
        # submit the request to the live server
        if response is None:   
            response = execution.submitRequest(request)
        else:
            response = etree.fromstring(response)
            
        if self.verbose==True:
            print etree.tostring(response)
            
        # parse response
        execution.parseResponse(response)
                        
        return execution
    
        
    def _parseProcessMetadata(self, rootElement):
        """
        Method to parse a <ProcessDescription> XML element and returned the constructed Process object
        """
        
        processDescriptionElement = rootElement.find( 'ProcessDescription' )
        process = Process(processDescriptionElement, verbose=self.verbose)
    
        # override existing processes in object metadata, if existing already
        found = False
        for n, p in enumerate(self.processes):
            if p.identifier==process.identifier:
                self.processes[n]=process
                found = True
        # otherwise add it
        if not found:
            self.processes.append(process)
            
        return process
                
        
    def _parseCapabilitiesMetadata(self, root):         
        ''' Sets up capabilities metadata objects '''
        
        # <ows:ServiceIdentification> metadata
        serviceIdentificationElement=root.find( util.nspath('ServiceIdentification', ns=DEFAULT_OWS_NAMESPACE) )
        #self.identification=ServiceIdentification(serviceIdentificationElement, namespace=OWS_NAMESPACE_1_1_0)
        self.identification=ServiceIdentification(serviceIdentificationElement)
        if self.verbose==True:
            dump(self.identification)
        
        # <ows:ServiceProvider> metadata
        serviceProviderElement=root.find( util.nspath('ServiceProvider', ns=DEFAULT_OWS_NAMESPACE) )
        self.provider=ServiceProvider(serviceProviderElement)  
        if self.verbose==True:
            dump(self.provider)
        
        # <ows:OperationsMetadata> metadata
        for operationElement in root.find( util.nspath('OperationsMetadata', ns=DEFAULT_OWS_NAMESPACE)):
            self.operations.append( OperationsMetadata(operationElement) )
            if self.verbose==True:
                dump(self.operations[-1])
                   
        # <wps:ProcessOfferings>
        #   <wps:Process ns0:processVersion="1.0.0">
        #     <ows:Identifier xmlns:ows="http://www.opengis.net/ows/1.1">gov.usgs.cida.gdp.wps.algorithm.filemanagement.ReceiveFiles</ows:Identifier>
        #     <ows:Title xmlns:ows="http://www.opengis.net/ows/1.1">gov.usgs.cida.gdp.wps.algorithm.filemanagement.ReceiveFiles</ows:Title>
        #   </wps:Process>
        #   ......
        # </wps:ProcessOfferings>
        for processElement in root.find( util.nspath('ProcessOfferings', ns=WPS_NAMESPACE)):
            p = Process(processElement, verbose=self.verbose)
            self.processes.append(p)
            if self.verbose==True:
                dump(self.processes[-1])
        
class WPSReader(object):
    """
    Superclass for reading a WPS document into a lxml.etree infoset.
    """

    def __init__(self, version=WPS_DEFAULT_VERSION, verbose=False):        
        self.version = version
        self.verbose = verbose
                
    def _readFromUrl(self, url, data, method='Get', username=None, password=None):
        """
        Method to get and parse a WPS document, returning an elementtree instance.
        url: WPS service base url.
        data: GET: dictionary of HTTP (key, value) parameter pairs, POST: XML document to post
        username, password: optional user credentials
        """
        
        if method == 'Get':
            # full HTTP request url
            request_url = build_get_url(url, data)
            if self.verbose==True:
                print request_url
    
            # split URL into base url and query string to use utility function
            spliturl=request_url.split('?')
            u = util.openURL(spliturl[0], spliturl[1], method='Get', username=username, password=password)
            return etree.fromstring(u.read())
        
        elif method == 'Post':
            u = util.openURL(url, data, method='Post', username = username, password = password)
            return etree.fromstring(u.read())
            
        else:
            raise Exception("Unrecognized HTTP method: %s" % method)
                
        
    def readFromString(self, string):
        """
        Method to read a WPS GetCapabilities document from an XML string.
        """
        
        if not isinstance(string, str):
            raise ValueError("Input must be of type string, not %s" % type(string))
        return etree.fromstring(string)    

class WPSCapabilitiesReader(WPSReader):
    """
    Utility class that reads and parses a WPS GetCapabilities document into a lxml.etree infoset.
    """
    
    def __init__(self, version=WPS_DEFAULT_VERSION, verbose=False):
        # superclass initializer
        super(WPSCapabilitiesReader,self).__init__(version=version, verbose=verbose)
        
    def readFromUrl(self, url, username=None, password=None):
        """
        Method to get and parse a WPS capabilities document, returning an elementtree instance.
        url: WPS service base url, to which is appended the HTTP parameters: service, version, and request.
        username, password: optional user credentials
        """
        return self._readFromUrl(url, 
                                 {'service':'WPS', 'request':'GetCapabilities', 'version':self.version}, 
                                 username=username, password=password)
            
class WPSDescribeProcessReader(WPSReader):
    """
    Class that reads and parses a WPS DescribeProcess document into a etree infoset
    """

    def __init__(self, version=WPS_DEFAULT_VERSION, verbose=False):
        # superclass initializer
        super(WPSDescribeProcessReader,self).__init__(version=version, verbose=verbose)

                
    def readFromUrl(self, url, identifier, username=None, password=None):
        """
        Reads a WPS DescribeProcess document from a remote service and returns the XML etree object
        url: WPS service base url, to which is appended the HTTP parameters: 'service', 'version', and 'request', and 'identifier'.
        """
        
        return self._readFromUrl(url, 
                                 {'service':'WPS', 'request':'DescribeProcess', 'version':self.version, 'identifier':identifier}, 
                                 username=username, password=password)
        
class WPSExecuteReader(WPSReader):
    """
    Class that reads and parses a WPS Execute response document into a etree infoset
    """
    def __init__(self, verbose=False):
        # superclass initializer
        super(WPSExecuteReader,self).__init__(verbose=verbose)
        
    def readFromUrl(self, url, data={}, method='Get', username=None, password=None):
         """
         Reads a WPS status document from a remote service and returns the XML etree object.
         url: the URL to submit the GET/POST request to.
         """
         
         return self._readFromUrl(url, data, method, username=username, password=password)

    
class WPSExecution():
    """
    Class that represents a single WPS process executed on a remote WPS service.
    """
    
    def __init__(self, version=WPS_DEFAULT_VERSION, url=None, username=None, password=None, verbose=False):
        
        # initialize fields
        self.url = url
        self.version = version
        self.username = username
        self.password = password
        self.verbose = verbose
        
        # status fields retrieved from the response documents
        self.process = None
        self.serviceInstance = None
        self.status = None
        self.errors = []
        self.statusLocation = None
        self.dataInputs=[]
        self.processOutputs=[]
        
    def buildRequest(self, identifier, inputs=[], output=None):
        """
        Method to build a WPS process request.
        identifier: the requested process identifier
        inputs: array of input arguments for the process.
            - LiteralData inputs are expressed as simple (key,value) tuples where key is the input identifier, value is the value
            - ComplexData inputs are express as (key, object) tuples, where key is the input identifier,
              and the object must contain a 'getXml()' method that returns an XML infoset to be included in the WPS request
        output: optional identifier if process output is to be returned as a hyperlink reference
        """
        
        #<wps:Execute xmlns:wps="http://www.opengis.net/wps/1.0.0" 
        #             xmlns:ows="http://www.opengis.net/ows/1.1" 
        #             xmlns:xlink="http://www.w3.org/1999/xlink" 
        #             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
        #             service="WPS" 
        #             version="1.0.0" 
        #             xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd">       
        root = etree.Element(util.nspath_eval('wps:Execute', namespaces))
        root.set('service', 'WPS')
        root.set('version', WPS_DEFAULT_VERSION)
        root.set('xmlns:ows', namespaces['ows'])
        root.set('xmlns:xlink', namespaces['xlink'])
        root.set(util.nspath_eval('xsi:schemaLocation', namespaces), '%s %s' % (namespaces['wps'], WPS_SCHEMA_LOCATION) )
        
        # <ows:Identifier>gov.usgs.cida.gdp.wps.algorithm.FeatureWeightedGridStatisticsAlgorithm</ows:Identifier>
        identifierElement = etree.SubElement(root, util.nspath_eval('ows:Identifier', namespaces))
        identifierElement.text = identifier
        
        # <wps:DataInputs>
        dataInputsElement = etree.SubElement(root, util.nspath_eval('wps:DataInputs', namespaces))
        
        for input in inputs:
            key = input[0]
            val = input[1]
            
            inputElement = etree.SubElement(dataInputsElement, util.nspath_eval('wps:Input', namespaces))
            identifierElement = etree.SubElement(inputElement, util.nspath_eval('ows:Identifier', namespaces))
            identifierElement.text = key
            
            # Literal data
            # <wps:Input>
            #   <ows:Identifier>DATASET_URI</ows:Identifier>
            #   <wps:Data>
            #     <wps:LiteralData>dods://igsarm-cida-thredds1.er.usgs.gov:8080/thredds/dodsC/dcp/conus_grid.w_meta.ncml</wps:LiteralData>
            #   </wps:Data>
            # </wps:Input>
            if isinstance(val, str):
                dataElement = etree.SubElement(inputElement, util.nspath_eval('wps:Data', namespaces))
                literalDataElement = etree.SubElement(dataElement, util.nspath_eval('wps:LiteralData', namespaces))
                literalDataElement.text = val
                
            # Complex data
            # <wps:Input>
            #   <ows:Identifier>FEATURE_COLLECTION</ows:Identifier>
            #   <wps:Reference xlink:href="http://igsarm-cida-gdp2.er.usgs.gov:8082/geoserver/wfs">
            #      <wps:Body>
            #        <wfs:GetFeature xmlns:wfs="http://www.opengis.net/wfs" xmlns:ogc="http://www.opengis.net/ogc" xmlns:gml="http://www.opengis.net/gml" service="WFS" version="1.1.0" outputFormat="text/xml; subtype=gml/3.1.1" xsi:schemaLocation="http://www.opengis.net/wfs ../wfs/1.1.0/WFS.xsd">
            #            <wfs:Query typeName="sample:CONUS_States">
            #                <wfs:PropertyName>the_geom</wfs:PropertyName>
            #                <wfs:PropertyName>STATE</wfs:PropertyName>
            #                <ogc:Filter>
            #                    <ogc:GmlObjectId gml:id="CONUS_States.508"/>
            #                </ogc:Filter>
            #            </wfs:Query>
            #        </wfs:GetFeature>
            #      </wps:Body>
            #   </wps:Reference>
            # </wps:Input>
            else:
               inputElement.append( val.getXml() )
        
        # <wps:ResponseForm>
        #   <wps:ResponseDocument storeExecuteResponse="true" status="true">
        #     <wps:Output asReference="true">
        #       <ows:Identifier>OUTPUT</ows:Identifier>
        #     </wps:Output>
        #   </wps:ResponseDocument>
        # </wps:ResponseForm>
        if output is not None:
            responseFormElement = etree.SubElement(root, util.nspath_eval('wps:ResponseForm', namespaces))
            responseDocumentElement = etree.SubElement(responseFormElement, util.nspath_eval('wps:ResponseDocument', namespaces), 
                                                       attrib={'storeExecuteResponse':'true', 'status':'true'} )
            outputElement = etree.SubElement(responseDocumentElement, util.nspath_eval('wps:Output', namespaces), 
                                                       attrib={'asReference':'true'} )
            outputIdentifierElement = etree.SubElement(outputElement, util.nspath_eval('ows:Identifier', namespaces)).text = output
                    
        return root
                
    # wait for 60 seconds by default
    def checkStatus(self, url=None, response=None, sleepSecs=60):
        """
        Method to check the status of a job execution.
        
        url: optional 'statusLocation' URL retrieved from a previous WPS Execute response document.
             If not provided, the current 'statusLocation' URL will be used.
        sleepSecs: number of seconds to sleep before returning control to the caller
        """
                    
        reader = WPSExecuteReader(verbose=self.verbose)
        if response is None:
            # override status location
            if url is not None:
                self.statusLocation = url
            print '\nChecking execution status... (location=%s)' % self.statusLocation
            response = reader.readFromUrl(self.statusLocation, username=self.username, password=self.password)
        else:
            response = reader.readFromString(response)
                
        if self.verbose==True:
            print etree.tostring(response)

        self.parseResponse(response)
                    
        # sleep given number of seconds
        if self.isComplete()==False:
            print 'Sleeping %d seconds...' % sleepSecs
            sleep(sleepSecs)

        
    def getStatus(self):
        return self.status
        
    def isComplete(self):
        if (self.status=='ProcessSucceeded' or self.status=='ProcessFailed' or self.status=='Exception'):
            return True
        elif (self.status=='ProcessStarted'):
            return False
        elif (self.status=='ProcessAccepted' or self.status=='ProcessPaused'):
            return False
        else:
            raise Exception('Unknown process execution status: %s' % self.status)
        
    def isSucceded(self):
         if self.status=='ProcessSucceeded':
             return True
         else:
             return False
        
    def isNotComplete(self):
        return not self.isComplete()
        
    def getOutput(self, filepath=None):
        """
        Method to retrieve the output of a WPS process from the remote server.
        
        filepath: optional path to the output file, otherwise a file will be created in the local directory with the name assigned by the server.
        """
        
        if self.isSucceded():
            for output in self.processOutputs:
                if output.reference is not None:
                    # a) 'http://cida.usgs.gov/climate/gdp/process/RetrieveResultServlet?id=1318528582026OUTPUT.601bb3d0-547f-4eab-8642-7c7d2834459e'
                    # b) 'http://rsg.pml.ac.uk/wps/wpsoutputs/outputImage-11294Bd6l2a.tif'
                    url = output.reference
                    if '?' in url:
                        spliturl=url.split('?')
                        u = util.openURL(spliturl[0], spliturl[1], method='Get', username = self.username, password = self.password)
                        # extract output filepath from URL query string
                        if filepath is None:
                            filepath = spliturl[1].split('=')[1]
                    else:
                        u = util.openURL(url, '', method='Get', username = self.username, password = self.password)
                        # extract output filepath from base URL
                        if filepath is None:
                            filepath = url.split('/')[-1]
                            print 'filepath=%s' % filepath
                    out = open(filepath, 'wb')
                    out.write(u.read())
                    out.close()
                    print 'Output written to file: %s' %filepath
                    
                if output.data is not None:
                    print output.data
            
        else:
            raise Exception("Execution not successfully completed: status=%s" % self.status)
    
    def submitRequest(self, request):
        """
        Submits a WPS Execute document to a remote service, returns the XML response document from the server.
        
        request: the XML request document to be submitted as POST to the server.
        """ 
        
        reader = WPSExecuteReader(verbose=self.verbose)
        response = reader.readFromUrl(self.url, request, method='Post', username=self.username, password=self.password)
        return response
 
        '''       
        if response is None:
            # override status location
            if url is not None:
                self.statusLocation = url
            
        else:
            response = reader.readFromString(response)

        
        '''
    
    def parseResponse(self, response):
        """
        Method to parse a WPS response document
        """
    
        rootTag = response.tag.split('}')[1]
        # <ns0:ExecuteResponse>
        if rootTag == 'ExecuteResponse':
            self._parseExecuteResponse(response)
                    
        # <ows:ExceptionReport>
        elif rootTag == 'ExceptionReport':
            self._parseExceptionReport(response)
            
        else:
            print 'Unknown Response'
            
        # print status, errors
        print 'Execution status=%s' % self.status
        for error in self.errors:
            dump(error)

            
    def _parseExceptionReport(self, root):
        """
        Method to parse a WPS ExceptionReport document and populate this object's metadata.
        """
        
        # set exception status, unless set already
        if self.status is None:
            self.status = "Exception"
            
        for exceptionEl in root.findall( util.nspath('Exception', ns=DEFAULT_OWS_NAMESPACE) ):
            self.errors.append( WPSException(exceptionEl) )


    def _parseExecuteResponse(self, root):      
        """
        Method to parse a WPS ExecuteResponse response document and populate this object's metadata.
        """
        
        self.serviceInstance = root.get( 'serviceInstance' )
        self.statusLocation = root.get( 'statusLocation' )
        # {http://www.opengis.net/wps/1.0.0}ProcessStarted
        statusEl = root.find( util.nspath('Status/*', ns=WPS_NAMESPACE) )
        self.status = statusEl.tag.split('}')[1]
        self.process = Process(root.find(util.nspath('Process', ns=WPS_NAMESPACE)), verbose=self.verbose)
        
        # exceptions ?
        exceptionEl = statusEl.find( util.nspath('ExceptionReport', ns=DEFAULT_OWS_NAMESPACE) )
        if exceptionEl is not None:
            self._parseExceptionReport(exceptionEl)
        
        #<wps:DataInputs xmlns:wps="http://www.opengis.net/wps/1.0.0"
        #                xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:xlink="http://www.w3.org/1999/xlink">
        for inputElement in root.findall( util.nspath('DataInputs/Input', ns='http://www.opengis.net/wps/1.0.0') ):
            self.dataInputs.append( Input(inputElement) )
            if self.verbose==True:
                dump(self.dataInputs[-1])
        
        # <ns:ProcessOutputs>
        # xmlns:ns="http://www.opengis.net/wps/1.0.0" 
        for outputElement in root.findall( util.nspath('ProcessOutputs/Output', ns=WPS_NAMESPACE)  ):
            self.processOutputs.append( Output(outputElement) )
            if self.verbose==True:
                dump(self.processOutputs[-1])
            
class ComplexData(object):
    """
    Class that represents a ComplexData element in a WPS document
    """
    
    def __init__(self, mimeType=None, encoding=None, schema=None):
        self.mimeType = mimeType
        self.encoding = encoding
        self.schema = schema

class InputOutput(object):
    """
    Superclass of a WPS input or output data object.
    """
    
    def __init__(self, element):
                
        # <ows:Identifier xmlns:ows="http://www.opengis.net/ows/1.1">SUMMARIZE_TIMESTEP</ows:Identifier>
        self.identifier = parseText( element.find( util.nspath('Identifier', ns=DEFAULT_OWS_NAMESPACE) ) )

        # <ows:Title xmlns:ows="http://www.opengis.net/ows/1.1">Summarize Timestep</ows:Title>
        self.title = parseText( element.find( util.nspath('Title', ns=DEFAULT_OWS_NAMESPACE) ) )
        
        # <ows:Abstract xmlns:ows="http://www.opengis.net/ows/1.1">If selected, processing output will include columns with summarized statistics for all feature attribute values for each timestep</ows:Abstract>
        self.abstract = parseText( element.find( util.nspath('Abstract', ns=DEFAULT_OWS_NAMESPACE) ) )
                
        self.allowedValues = []
        self.supportedValues = []
        self.defaultValue = None
        self.dataType = None
        
    def _parseData(self, element):
        """
        Method to parse a "Data" element
        """
        
        # <ns0:Data>
        #        <ns0:ComplexData mimeType="text/plain">
        #             7504912.93758151 -764109.175074507,7750849.82379226 -22141.8611641468,8561828.42371234 -897195.923493867,7724946.16844165 -602984.014261927 
        #        </ns0:ComplexData>
        # </ns0:Data>
        #util.nspath('Data', ns=WPS_NAMESPACE)
        complexDataElement = element.find( util.nspath('ComplexData', ns=WPS_NAMESPACE) )
        if complexDataElement is not None:
            self.dataType = "ComplexData"
            
        print 'found: %s' % complexDataElement

        
    def _parseLiteralData(self, element, literalElementName):
        """
        Method to parse the LiteralData element.
        """
        
        # <LiteralData>
        #    <ows:DataType ows:reference="xs:string" xmlns:ows="http://www.opengis.net/ows/1.1" />
        #    <ows:AllowedValues xmlns:ows="http://www.opengis.net/ows/1.1">
        #        <ows:Value>COMMA</ows:Value>
        #        <ows:Value>TAB</ows:Value>
        #        <ows:Value>SPACE</ows:Value>
        #    </ows:AllowedValues>
        #    <DefaultValue>COMMA</DefaultValue>
        # </LiteralData>
        
        # <LiteralData>
        #     <ows:DataType ows:reference="xs:anyURI" xmlns:ows="http://www.opengis.net/ows/1.1" />
        #     <ows:AnyValue xmlns:ows="http://www.opengis.net/ows/1.1" />
        # </LiteralData>
        literalDataElement = element.find( literalElementName )
        if literalDataElement is not None:
            dataTypeElement = literalDataElement.find( util.nspath('DataType', ns=DEFAULT_OWS_NAMESPACE) ) 
            self.dataType = dataTypeElement.get( util.nspath("reference", ns=DEFAULT_OWS_NAMESPACE) ).split(':')[1]
            for value in literalDataElement.findall( util.nspath('AllowedValues/Value', ns=DEFAULT_OWS_NAMESPACE) ):
                self.allowedValues.append( getTypedValue(self.dataType, value.text) )
            defaultValue = literalDataElement.find( 'DefaultValue' ) 
            if defaultValue is not None:
                self.defaultValue = getTypedValue(self.dataType, defaultValue.text)    

    def _parseComplexData(self, element, complexDataElementName):
        """
        Method to parse a ComplexData or ComplexOutput element.
        """
        
        # <ComplexData>
        #     <Default>
        #         <Format>
        #            <MimeType>text/xml</MimeType>
        #            <Encoding>UTF-8</Encoding>
        #            <Schema>http://schemas.opengis.net/gml/2.0.0/feature.xsd</Schema>
        #        </Format>
        #    </Default>
        #    <Supported>
        #        <Format>
        #            <MimeType>text/xml</MimeType>
        #            <Encoding>UTF-8</Encoding>
        #            <Schema>http://schemas.opengis.net/gml/2.0.0/feature.xsd</Schema>
        #        </Format>
        #        <Format>
        #            <MimeType>text/xml</MimeType>
        #            <Encoding>UTF-8</Encoding>
        #            <Schema>http://schemas.opengis.net/gml/2.1.1/feature.xsd</Schema>
        #        </Format>
        #    </Supported>
        # </ComplexData>
        complexDataElement = element.find( complexDataElementName )
        if complexDataElement is not None:
            self.dataType = "ComplexData"
            
            for formatElement in complexDataElement.findall( 'Supported/Format'):
                self.supportedValues.append( ComplexData( mimeType=parseText( formatElement.find( 'MimeType' ) ),
                                                          encoding=parseText( formatElement.find( 'Encoding' ) ),
                                                          schema=parseText( formatElement.find( 'Schema' ) ) 
                                                         ) 
                )
               
            defaultFormatElement = complexDataElement.find( 'Default/Format' ) 
            if defaultFormatElement is not None:
                self.defaultValue = ComplexData( mimeType=parseText( defaultFormatElement.find( 'MimeType' ) ),
                                                 encoding=parseText( defaultFormatElement.find( 'Encoding' ) ),
                                                 schema=parseText( defaultFormatElement.find( 'Schema' ) ) 
                                               ) 


class Input(InputOutput):
    """
    Class that represents a WPS process input.
    """
    
    def __init__(self, inputElement):
        
        # superclass initializer
        super(Input,self).__init__(inputElement)
        
        # <Input maxOccurs="1" minOccurs="0">
        if inputElement.get("minOccurs") is not None:
            self.minOccurs = int( inputElement.get("minOccurs") )
        else:
            self.minOccurs = -1
        if inputElement.get("maxOccurs") is not None:
            self.maxOccurs = int( inputElement.get("maxOccurs") )
        else:
            self.maxOccurs = -1
        
        # <LiteralData>
        self._parseLiteralData(inputElement, 'LiteralData')
                
        # <ComplexData>
        self._parseComplexData(inputElement, 'ComplexData')
                
    
class Output(InputOutput):
    """
    Class that represents a WPS process output.
    """
    
    def __init__(self, outputElement):
    
        # superclass initializer
        super(Output,self).__init__(outputElement)
        
        self.reference = None
        self.mimeType = None
        self.data = None
        
        # <ns:Reference encoding="UTF-8" mimeType="text/csv"
        #     href="http://cida.usgs.gov/climate/gdp/process/RetrieveResultServlet?id=1318528582026OUTPUT.601bb3d0-547f-4eab-8642-7c7d2834459e" />
        referenceElement = outputElement.find( util.nspath('Reference', ns=WPS_NAMESPACE) )
        if referenceElement is not None:
            self.reference = referenceElement.get('href')
            self.mimeType = referenceElement.get('mimeType')
       
        # <LiteralData>
        self._parseLiteralData(outputElement, 'LiteralData')
        
        # <ComplexData>
        self._parseComplexData(outputElement, 'ComplexOutput')
        
        # <Data>
        dataElement = outputElement.find( util.nspath('Data', ns=WPS_NAMESPACE) )       
        # <ns0:Data>
        #        <ns0:ComplexData mimeType="text/plain">
        #             7504912.93758151 -764109.175074507,7750849.82379226 -22141.8611641468,8561828.42371234 -897195.923493867,7724946.16844165 -602984.014261927 
        #        </ns0:ComplexData>
        # </ns0:Data>
        #util.nspath('Data', ns=WPS_NAMESPACE)
        if dataElement is not None:
            complexDataElement = dataElement.find( util.nspath('ComplexData', ns=WPS_NAMESPACE) )
            if complexDataElement is not None:
                self.dataType = "ComplexData"
                self.mimeType = complexDataElement.get('mimeType')
                self.data = complexDataElement.text
                    
class WPSException:
    """
    Class representing an exception raised by a WPS.
    """
    
    def __init__(self, root):
        self.code = root.attrib.get("exceptionCode", None)
        self.locator = root.attrib.get("locator", None)
        textEl = root.find( util.nspath('ExceptionText', ns=DEFAULT_OWS_NAMESPACE) )
        if textEl is not None:
            self.text = textEl.text
        else:
            self.text = ""

class Process(object):
    """
    Class that represents a WPS process.
    """
    
    def __init__(self, elem, verbose=False):
        """ Initialization method extracts all available metadata from an XML document (passed in as etree object) """
        
        # <ns0:ProcessDescriptions service="WPS" version="1.0.0" 
        #                          xsi:schemaLocation="http://www.opengis.net/wps/1.0.0 http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_response.xsd" 
        #                          xml:lang="en-US" xmlns:ns0="http://www.opengis.net/wps/1.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        # OR:
        # <ns0:Process ns0:processVersion="1.0.0">
        self._root = elem
        self.verbose = verbose
        
        # <ProcessDescription statusSupported="true" storeSupported="true" ns0:processVersion="1.0.0">
        self.processVersion = elem.get( util.nspath('processVersion', ns=WPS_NAMESPACE) )
        self.statusSupported = bool( elem.get( "statusSupported" ) )
        self.storeSupported = bool( elem.get( "storeSupported" ) )
        
        # <ows:Identifier xmlns:ows="http://www.opengis.net/ows/1.1">gov.usgs.cida.gdp.wps.algorithm.FeatureWeightedGridStatisticsAlgorithm</ows:Identifier>
        self.identifier = parseText( elem.find( util.nspath('Identifier', ns=DEFAULT_OWS_NAMESPACE) ) )
        
        # <ows:Title xmlns:ows="http://www.opengis.net/ows/1.1">Feature Weighted Grid Statistics</ows:Title>
        self.title =  parseText( elem.find( util.nspath('Title', ns=DEFAULT_OWS_NAMESPACE) ) )
        
        # <ows:Abstract xmlns:ows="http://www.opengis.net/ows/1.1">This algorithm generates area weighted statistics of a gridded dataset for a set of vector polygon features. Using the bounding-box that encloses the feature data and the time range, if provided, a subset of the gridded dataset is requested from the remote gridded data server. Polygon representations are generated for cells in the retrieved grid. The polygon grid-cell representations are then projected to the feature data coordinate reference system. The grid-cells are used to calculate per grid-cell feature coverage fractions. Area-weighted statistics are then calculated for each feature using the grid values and fractions as weights. If the gridded dataset has a time range the last step is repeated for each time step within the time range or all time steps if a time range was not supplied.</ows:Abstract>
        self.abstract = parseText( elem.find( util.nspath('Abstract', ns=DEFAULT_OWS_NAMESPACE) ) )
        
        if self.verbose==True:
            dump(self)
        
        # <DataInputs>
        self.dataInputs = []
        for inputElement in elem.findall( 'DataInputs/Input' ):
            self.dataInputs.append( Input(inputElement) )
            if self.verbose==True:
                dump(self.dataInputs[-1], prefix='\tInput: ')
        
        # <ProcessOutputs>
        self.processOutputs = []
        for outputElement in elem.findall( 'ProcessOutputs/Output' ):
            self.processOutputs.append( Output(outputElement) )
            if self.verbose==True:
                dump(self.processOutputs[-1],  prefix='\tOutput: ')
     
    
class FeatureCollection():
    '''
    Base class to represent a Feature Collection used as input to a WPS request.
    The method getXml() is invoked by the WPS execute() method to build the WPS request.
    All subclasses must implement the getXml() method to provide their specific XML.
    '''
    
    def __init__(self):
        pass
    
    def getXml(self):
        raise NotImplementedError
    
class WFSFeatureCollection(FeatureCollection):
    '''
    FeatureCollection specified by a WFS query.
    All subclasses must implement the getQuery() method to provide the specific query portion of the XML.
    '''
    
    def __init__(self, wfsUrl, wfsQuery):
        '''
        wfsUrl: the WFS service URL
                example: wfsUrl = "http://igsarm-cida-gdp2.er.usgs.gov:8082/geoserver/wfs"
        wfsQuery : a WFS query instance
        '''
        self.url = wfsUrl
        self.query = wfsQuery
    
    #    <wps:Reference xlink:href="http://igsarm-cida-gdp2.er.usgs.gov:8082/geoserver/wfs">
    #      <wps:Body>
    #        <wfs:GetFeature xmlns:wfs="http://www.opengis.net/wfs" xmlns:ogc="http://www.opengis.net/ogc" xmlns:gml="http://www.opengis.net/gml" service="WFS" version="1.1.0" outputFormat="text/xml; subtype=gml/3.1.1" xsi:schemaLocation="http://www.opengis.net/wfs ../wfs/1.1.0/WFS.xsd">
    #            .......
    #        </wfs:GetFeature>
    #      </wps:Body>
    #   </wps:Reference>
    def getXml(self):
        
        root = etree.Element(util.nspath_eval('wps:Reference', namespaces),
                             attrib = { "xlink:href" : self.url} )
        bodyElement = etree.SubElement(root, util.nspath_eval('wps:Body', namespaces))
        getFeatureElement = etree.SubElement(bodyElement, util.nspath_eval('wfs:GetFeature', namespaces),
                                             attrib = { "service":"WFS",
                                                        "version":"1.1.0",
                                                        "xmlns:ogc":namespaces['ogc'],
                                                        "xmlns:gml":namespaces['gml'],
                                                        "xmlns:xsi":namespaces['xsi'],
                                                        "outputFormat":"text/xml; subtype=gml/3.1.1",
                                                        "xsi:schemaLocation":"%s %s" % (namespaces['wfs'], '../wfs/1.1.0/WFS.xsd')})
        
        #            <wfs:Query typeName="sample:CONUS_States">
        #                <wfs:PropertyName>the_geom</wfs:PropertyName>
        #                <wfs:PropertyName>STATE</wfs:PropertyName>
        #                <ogc:Filter>
        #                    <ogc:GmlObjectId gml:id="CONUS_States.508"/>
        #                </ogc:Filter>
        #            </wfs:Query>
        getFeatureElement.append( self.query.getXml() )
        
        return root
    
class WFSQuery():
    '''
    Class representing a WFS query, for insertion into a WFSFeatureCollection instance.
    '''
    
    def __init__(self, typeName, propertyNames=[], filters=[]):
        self.typeName = typeName
        self.propertyNames = propertyNames
        self.filters = filters
        
    def getXml(self):
        
        #            <wfs:Query typeName="sample:CONUS_States">
        #                <wfs:PropertyName>the_geom</wfs:PropertyName>
        #                <wfs:PropertyName>STATE</wfs:PropertyName>
        #                <ogc:Filter>
        #                    <ogc:GmlObjectId gml:id="CONUS_States.508"/>
        #                </ogc:Filter>
        #            </wfs:Query>
   
        queryElement = etree.Element(util.nspath_eval('wfs:Query', namespaces), attrib = { "typeName":self.typeName })
        for propertyName in self.propertyNames:
            propertyNameElement = etree.SubElement(queryElement, util.nspath_eval('wfs:PropertyName', namespaces))
            propertyNameElement.text = propertyName
        if len(self.filters)>0:
            filterElement = etree.SubElement(queryElement, util.nspath_eval('ogc:Filter', namespaces))
            for filter in self.filters:
                gmlObjectIdElement = etree.SubElement(filterElement, util.nspath_eval('ogc:GmlObjectId', namespaces), 
                                                      attrib={util.nspath_eval('gml:id', namespaces):filter})
        return queryElement
        
class GMLMultiPolygonFeatureCollection(FeatureCollection):
    '''
    Class that represents a FeatureCollection defined as a GML multi-polygon.
    '''
    
    def __init__(self, polygons):
        '''
        Initializer accepts an array of polygons, where each polygon is an array of (lat,lon) tuples.
        Example: polygons = [ [(-102.8184, 39.5273), (-102.8184, 37.418), (-101.2363, 37.418), (-101.2363, 39.5273), (-102.8184, 39.5273)],
                              [(-92.8184, 39.5273), (-92.8184, 37.418), (-91.2363, 37.418), (-91.2363, 39.5273), (-92.8184, 39.5273)] ]
        '''
        self.polygons = polygons
    
    def getXml(self):
        '''
            <wps:Data>
                <wps:ComplexData mimeType="text/xml" encoding="UTF-8"
                    schema="http://schemas.opengis.net/gml/3.1.1/base/feature.xsd">
                    <gml:featureMembers xmlns:ogc="http://www.opengis.net/ogc"
                        xmlns:draw="gov.usgs.cida.gdp.draw" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                        xmlns:ows="http://www.opengis.net/ows" xmlns:gml="http://www.opengis.net/gml"
                        xmlns:xlink="http://www.w3.org/1999/xlink"
                        xsi:schemaLocation="gov.usgs.cida.gdp.draw http://cida.usgs.gov/qa/climate/derivative/xsd/draw.xsd">
                        <gml:box gml:id="box.1">
                            <gml:the_geom>
                                <gml:MultiPolygon srsDimension="2"
                                    srsName="http://www.opengis.net/gml/srs/epsg.xml#4326">
                                    <gml:polygonMember>
                                        <gml:Polygon>
                                            <gml:exterior>
                                                <gml:LinearRing>
                                                    <gml:posList>-102.8184 39.5273 -102.8184 37.418 -101.2363 37.418 -101.2363 39.5273 -102.8184 39.5273</gml:posList>
                                                </gml:LinearRing>
                                            </gml:exterior>
                                        </gml:Polygon>
                                    </gml:polygonMember>
                                </gml:MultiPolygon>
                            </gml:the_geom>
                            <gml:ID>0</gml:ID>
                        </gml:box>
                    </gml:featureMembers>
                </wps:ComplexData>
            </wps:Data>
        '''
        dataElement = etree.Element(util.nspath_eval('wps:Data', namespaces))
        complexDataElement = etree.SubElement(dataElement, util.nspath_eval('wps:ComplexData', namespaces),
                                              attrib={"mimeType":"text/xml", "encoding":"UTF-8", "schema":GML_SCHEMA_LOCATION} )
        featureMembersElement = etree.SubElement(complexDataElement, util.nspath_eval('gml:featureMembers', namespaces),
                                                 attrib={"xmlns:ogc":OGC_NAMESPACE, 
                                                         "xmlns:draw":DRAW_NAMESPACE,
                                                         "xmlns:ows":OWS_NAMESPACE_1_0_0,
                                                         #"xmlns:gml":GML_NAMESPACE,
                                                         "xmlns:xlink":XLINK_NAMESPACE,
                                                         "xsi:schemaLocation":"%s %s" % (DRAW_NAMESPACE, DRAW_SCHEMA_LOCATION)})
        boxElement = etree.SubElement(featureMembersElement, util.nspath_eval('gml:box', namespaces), attrib={"gml:id":"box.1"})
        geomElement = etree.SubElement(boxElement, util.nspath_eval('gml:the_geom', namespaces))
        multiPolygonElement = etree.SubElement(geomElement, util.nspath_eval('gml:MultiPolygon', namespaces),
                                               attrib={"srsDimension":"2", "srsName":"http://www.opengis.net/gml/srs/epsg.xml#4326"} )
        for polygon in self.polygons:
            polygonMemberElement = etree.SubElement(multiPolygonElement, util.nspath_eval('gml:polygonMember', namespaces))
            polygonElement = etree.SubElement(polygonMemberElement, util.nspath_eval('gml:Polygon', namespaces))
            exteriorElement = etree.SubElement(polygonElement, util.nspath_eval('gml:exterior', namespaces))
            linearRingElement = etree.SubElement(exteriorElement, util.nspath_eval('gml:LinearRing', namespaces))
            posListElement = etree.SubElement(linearRingElement, util.nspath_eval('gml:posList', namespaces))
            posListElement.text =  ' '.join(["%s %s" % (x, y) for x, y in polygon[:] ])
        
        idElement = etree.SubElement(boxElement, util.nspath_eval('gml:ID', namespaces))
        idElement.text = "0"
        return dataElement