import os, re, sys, logging

import numpy as np
import subprocess as sp
import cPickle as pickle

from pdb import set_trace

sys.path.insert(0, os.path.dirname(os.getcwd()))
from Core.CoreSystem import CoreHash, CoreGotoh


class clsParameter(object):

    def __init__(self):

        if len(sys.argv) > 1:
            self.strForwardFqPath = sys.argv[1]
            self.strReverseFqPath = sys.argv[2]
            self.strRefFa         = sys.argv[3]
            self.strPair          = sys.argv[4]
            self.floOg            = float(sys.argv[5])
            self.floOe            = float(sys.argv[6])
            self.intInsertionWin  = int(sys.argv[7])
            self.intDeletionWin   = int(sys.argv[8])
            self.strPamType       = sys.argv[9].upper()  ## Cpf1, Cas9
            self.strBarcodePamPos = sys.argv[10]  ## PAM - BARCODE type (reverse) or BARCODE - PAM type (forward)
            self.intQualCutoff    = int(sys.argv[11])  ## default = 20
            self.strOutputdir     = sys.argv[12]
            self.strLogPath       = sys.argv[13]
            self.strEDNAFULL      = os.path.abspath('../EDNAFULL')

        else:
            sManual = """
            Usage:

            python2.7 ./indel_search_ver1.0.py splitted_input_1.fq splitted_input_2.fq reference.fa

            splitted_input_1.fq : forward
            splitted_input_2.fq : reverse

            Total FASTQ(fq) lines / 4 = remainder 0.
            """
            print(sManual)
            sys.exit()


class clsFastqOpener(object):

    def __init__(self, InstParameter):

        self.strForwardFqPath = InstParameter.strForwardFqPath
        self.strReverseFqPath = InstParameter.strReverseFqPath
    """
    :return [tuples array]
        [(Sequence identifier,Nucleotide sequence, [Quality scores array]),(seq, qual)]
        ex) tuple : (@MN00416:88:000H2WVH3:1:11101:17048:1168 1:N:0:1
            , GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
            , [37,32,37,37,37,37,37,37 insted of FAFFFFFF...
            )
    """
    def OpenFastqForward(self):

        listFastqForward = []
        listStore        = []

        with open(self.strForwardFqPath) as Fastq1:

            for i, strRow in enumerate(Fastq1):

                i = i + 1
                strRow = strRow.replace('\n', '').upper()

                if i % 4 == 1 or i % 4 == 2:
                    listStore.append(strRow)
                elif i % 4 == 0:
                    """change Symbol to Quality-Score(https://bit.ly/2OLYC6m)"""
                    listQual = [ord(i) - 33 for i in strRow]
                    listStore.append(listQual)
                    listFastqForward.append(tuple(listStore))
                    listStore = []

        return listFastqForward

    def OpenFastqReverse(self):

        listFastqReverse = []
        listStore        = []

        dictRev = {'A': 'T', 'C': 'G', 'G': 'C', 'T': 'A', 'N': 'N'}

        #with open('./6_AsD0_2_small_test.fq') as fa_2:
        with open(self.strReverseFqPath) as Fastq2:

            for i, strRow in enumerate(Fastq2):
                i = i + 1
                strRow = strRow.replace('\n', '').upper()

                if i % 4 == 1:
                    listStore.append(strRow)
                elif i % 4 == 2:
                    listStore.append(''.join([dictRev[strNucle] for strNucle in strRow[::-1]]))
                elif i % 4 == 0:
                    """change Symbol to Quality-Score(https://bit.ly/2OLYC6m)"""
                    listQual = [ord(i) - 33 for i in strRow][::-1]
                    listStore.append(listQual)
                    listFastqReverse.append(tuple(listStore))
                    listStore = []

        return listFastqReverse
        #end1: return
    #end: def


class clsIndelSearchParser(object):

    def __init__(self, InstParameter):

        # index name, constant variable.
        self.intNumOfTotal = 0
        self.intNumOfIns   = 1
        self.intNumOfDel   = 2
        self.intNumofCom   = 3
        self.intTotalFastq = 4
        self.intInsFastq   = 5
        self.intDelFastq   = 6
        self.intComFastq   = 7
        self.intIndelInfo  = 8

        self.strRefFa        = InstParameter.strRefFa
        self.floOg           = InstParameter.floOg
        self.floOe           = InstParameter.floOe
        self.strEDNAFULL     = InstParameter.strEDNAFULL
        self.strPamType      = InstParameter.strPamType
        self.intInsertionWin = InstParameter.intInsertionWin
        self.intDeletionWin  = InstParameter.intDeletionWin
        self.intQualCutoff   = InstParameter.intQualCutoff

    def SearchBarcodeIndelPosition(self, sBarcode_PAM_pos):

        dRef    = {}
        dResult = {}
        """
        self.strRefFa ... Reference.fa is made with 
                            > Barcode.txt : Target_region.txt
                            Reference_sequence.txt
        """
        with open(self.strRefFa) as Ref:

            sBarcode       = ""
            sTarget_region = ""
            intBarcodeLen  = 0

            for i, sRow in enumerate(Ref):

                if i % 2 == 0: ## >CGCTCTACGTAGACA:CTCTATTACTCGCCCCACCTCCCCCAGCCC
                    """
                    sBarcode ... CGCTCTACGTAGACA
                    sTarget_region ... CTCTATTACTCGCCCCACCTCCCCCAGCCC
                    """
                    sBarcode, sTarget_region, intBarcodeLen = self._SeperateFaHeader(sRow, sBarcode, sTarget_region,
                                                                                    intBarcodeLen, sBarcode_PAM_pos)

                elif i % 2 != 0: ## AGCATCGATCAGCTACGATCGATCGATCACTAGCTACGATCGATCA
                    """
                    sRef_seq ... sRow without new line
                    iIndel_start_pos ... start index of sTarget_region in sRef_seq
                    iIndel_end_pos ... end index of sTarget_region in sRef_seq
                    """
                    sRef_seq, iIndel_start_pos, iIndel_end_pos = self._SearchIndelPos(sRow, sBarcode_PAM_pos, sTarget_region)

                    try:
                        self._MakeRefAndResultTemplate(sRef_seq, sBarcode, iIndel_start_pos, iIndel_end_pos,
                                                       sTarget_region, dRef, dResult)
                    except ValueError:
                        continue

        assert len(dRef.keys()) == len(dResult.keys())
        """
        dRef[sBarcode] = (sRef_seq, sTarget_region, sRef_seq_after_barcode, iIndel_start_next_pos_from_barcode_end,
                          iIndel_end_next_pos_from_barcode_end, iIndel_start_pos, iIndel_end_pos)  
                          # total matched reads, insertion, deletion, complex
        # lRef   : [(ref_seq, ref_seq_after_barcode, barcode, barcode end pos, indel end pos, indel from barcode),(...)]
        
        ## iIndel_start_next_pos_from_barcode_end = start index of target region in sRef_seq WOUT BARCD SEQ 
        ## iIndel_end_next_pos_from_barcode_end = end index of target region in sRef_seq WOUT BARCD SEQ
        ## iIndel_start_pos ... start index of sTarget_region in sRef_seq
        ## iIndel_end_pos ... end index of sTarget_region in sRef_seq

        dResult[sBarcode] = [0, 0, 0, 0, [], [], [], [], []]
        # dResult = [# of total, # of ins, # of del, # of com, [total FASTQ], [ins FASTQ], [del FASTQ], [com FASTQ]]
        """
        return dRef, dResult
        # end1: return

    def _SeperateFaHeader(self, sRow, sBarcode, sTarget_region, intBarcodeLen, sBarcode_PAM_pos):

        #      barcode               target region
        # >CGCTCTACGTAGACA:CTCTATTACTCGCCCCACCTCCCCCAGCCC
        sBarcode_indel_seq = sRow.strip().replace('\n', '').replace('\r', '').split(':')
        sBarcode           = sBarcode_indel_seq[0].replace('>', '')

        if intBarcodeLen > 0:
            assert intBarcodeLen == len(sBarcode), 'All of the barcode lengths must be same.'
        intBarcodeLen = len(sBarcode)

        sTarget_region = sBarcode_indel_seq[1]

        ## Reverse the sentence. If it is done, all methods are same before work.
        if sBarcode_PAM_pos == 'Reverse':
            sBarcode = sBarcode[::-1]
            sTarget_region = sTarget_region[::-1]

        return (sBarcode, sTarget_region, intBarcodeLen)

    def _SearchIndelPos(self, sRow, sBarcode_PAM_pos, sTarget_region):

        sRef_seq = sRow.strip().replace('\n', '').replace('\r', '')

        if sBarcode_PAM_pos == 'Reverse':
            sRef_seq = sRef_seq[::-1]

        Seq_matcher = re.compile(r'(?=(%s))' % sTarget_region)
        # iIndel_start_pos       = sRef_seq.index(sTarget_region)               # There is possible to exist two indel.
        iIndel_start_pos = Seq_matcher.finditer(sRef_seq)

        for i, match in enumerate(iIndel_start_pos):
            iIndel_start_pos = match.start()
        # print iIndel_start_pos
        # print len(sTarget_region)
        # print sRef_seq
        iIndel_end_pos = iIndel_start_pos + len(sTarget_region) - 1

        return (sRef_seq, iIndel_start_pos, iIndel_end_pos)

    def _MakeRefAndResultTemplate(self, sRef_seq, sBarcode, iIndel_start_pos,
                                 iIndel_end_pos, sTarget_region, dRef, dResult):
        iBarcode_start_pos = sRef_seq.index(sBarcode)

        # if iIndel_start_pos <= iBarcode_start_pos:
        #    print(iIndel_start_pos, iBarcode_start_pos)
        #    raise IndexError('indel is before barcode')

        iBarcode_end_pos       = iBarcode_start_pos + len(sBarcode) - 1
        sRef_seq_after_barcode = sRef_seq[iBarcode_end_pos + 1:]

        # modified. to -1
        iIndel_end_next_pos_from_barcode_end   = iIndel_end_pos - iBarcode_end_pos - 1
        iIndel_start_next_pos_from_barcode_end = iIndel_start_pos - iBarcode_end_pos - 1

        #  "barcode"-------------*(N) that distance.
        #          ^  ^            ^
        #   *NNNN*NNNN
        #    ^    ^     indel pos, the sequence matcher selects indel event pos front of it.

        ## Result
        dRef[sBarcode] = (sRef_seq, sTarget_region, sRef_seq_after_barcode, iIndel_start_next_pos_from_barcode_end,
                          iIndel_end_next_pos_from_barcode_end, iIndel_start_pos, iIndel_end_pos)  # total matched reads, insertion, deletion, complex
        dResult[sBarcode] = [0, 0, 0, 0, [], [], [], [], []]

    """
    lFASTQ = [(Sequence identifier,Nucleotide sequence, Quality scores array),(seq, qual)]
        ex) (@MN00416:88:000H2WVH3:1:11101:17048:1168 1:N:0:1
            , GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
            , [37,32,37,37,37,37,37,37 insted of FAFFFFFF...
            )
    dRef[sBarcode] = (sRef_seq, sTarget_region, sRef_seq_after_barcode, iIndel_start_next_pos_from_barcode_end,
                      iIndel_end_next_pos_from_barcode_end, iIndel_start_pos, iIndel_end_pos)  
                      # total matched reads, insertion, deletion, complex

    ## iIndel_start_next_pos_from_barcode_end = start index of target region in sRef_seq WOUT BARCD SEQ 
    ## iIndel_end_next_pos_from_barcode_end = end index of target region in sRef_seq WOUT BARCD SEQ
    ## iIndel_start_pos ... start index of sTarget_region in sRef_seq
    ## iIndel_end_pos ... end index of sTarget_region in sRef_seq

    dResult[sBarcode] = [0, 0, 0, 0, [], [], [], [], []]
    sBarcode_PAM_pos is ... PAM position: Forward Reverse
    """
    def SearchIndel(self, lFASTQ=[], dRef = {}, dResult={}, sBarcode_PAM_pos=""):

        # lFASTQ : [(seq, qual),(seq, qual)]
        # lRef   : [(ref_seq, ref_seq_after_barcode, barcode, barcode end pos, indel end pos, indel from barcode),(...)]
        # dResult = [# of total, # of ins, # of del, # of com, [total FASTQ], [ins FASTQ], [del FASTQ], [com FASTQ]]
        iCount = 0
        intBarcodeLen = len(dRef.keys()[0])
        #print('intBarcodeLen', intBarcodeLen)

        InstGotoh = CoreGotoh(strEDNAFULL=self.strEDNAFULL, floOg=self.floOg, floOe=self.floOe)

        for lCol_FASTQ in lFASTQ:
            sName = lCol_FASTQ[0]  # @MN00416:88:000H2WVH3:1:11101:17048:1168 1:N:0:1
            if sBarcode_PAM_pos == 'Reverse':
                sSeq  = lCol_FASTQ[1][::-1]
                lQual = lCol_FASTQ[2][::-1]
            else:
                sSeq  = lCol_FASTQ[1]  # GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
                lQual = lCol_FASTQ[2]  # [37,32,37,37,37,37,37,37 insted of FAFFFFFF...

            assert isinstance(sName, str) and isinstance(sSeq, str) and isinstance(lQual, list)
            """
            if sSeq = 'GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGG...' and intBarcodeLen = 7
            listSeqWindow = ['GAATCTA','AATCTAC','ATCTACT', ...., 'TCAGCGG']
            """
            listSeqWindow = CoreHash.MakeHashTable(sSeq, intBarcodeLen)

            iBarcode_matched = 0
            iInsert_count    = 0
            iDelete_count    = 0
            iComplex_count   = 0

            intFirstBarcode  = 0 ## check whether a barcode is one in a sequence.

            for strSeqWindow in listSeqWindow:

                if intFirstBarcode == 1: break ## A second barcode in a sequence is not considerable.

                try:
                    """
                    lCol_ref = dRef[strSeqWindow] = (sRef_seq, sTarget_region, sRef_seq_after_barcode, iIndel_start_next_pos_from_barcode_end,
                          iIndel_end_next_pos_from_barcode_end, iIndel_start_pos, iIndel_end_pos)  
                    sBarcode = strSeqWindow
                    intFirstBarcode = 1 , if dRef dict value (=lCol_ref) is existed by key == strSeqWindow
                    """
                    lCol_ref, sBarcode, intFirstBarcode = CoreHash.IndexHashTable(dRef, strSeqWindow, intFirstBarcode)
                except KeyError:
                    continue

                sRef_seq                      = lCol_ref[0]
                sTarget_region                = lCol_ref[1]  # ref_seq_after_barcode
                iIndel_seq_len                = len(sTarget_region)
                sRef_seq_after_barcode        = lCol_ref[2]  # sRef_seq_after_barcode
                iIndel_start_from_barcode_pos = lCol_ref[3]  # iIndel_start_next_pos_from_barcode_end  = start index
                # of target_region in sRef_seq WOUT BARCD SEQ
                iIndel_end_from_barcode_pos   = lCol_ref[4]  # iIndel_end_next_pos_from_barcode_end  = end of
                # target_region in sRef_seq WOUT BARCD SEQ
                try:
                    """
                    iIndel_end_from_barcode_pos = iIndel_end_next_pos_from_barcode_end  = end of target_region in sRef_seq WOUT BARCD SEQ
                    iKbp_front_Indel_end = cleavege point(index) from end index of PAM
                                        cleavege point(index) from end of target_region in sRef_seq WOUT BARCD SEQ
                    """
                    if self.strPamType == 'CAS9':
                        iKbp_front_Indel_end = iIndel_end_from_barcode_pos - 6  ## cas9:-6, cpf1:-4
                    elif self.strPamType == 'CPF1':
                        iKbp_front_Indel_end = iIndel_end_from_barcode_pos - 4  ## NN(N)*NNN(N)*NNNN
                except Exception:
                    set_trace()

                """
                                                     *     ^ : iIndel_end_from_barcode_pos
                                  GGCG   TCGCTCATGTACCTCCCGT
                TATAGTCTGTCATGCGATGGCG---TCGCTCATGTACCTCCCGTTACAGCCACAAAGCAGGA
                     *
                GGCGTC GCTCATGTACCTCCCGT
                  6          17 
                """

                ## bug fix
                if sBarcode == "": continue
                """
                :param 
                    sSeq = GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
                    sBarcode = strSeqWindow
                    iBarcode_matched = 0 (value for initial)
                    lQual =  [37,32,37,37,37,37,37,37 insted of FAFFFFFF...
                :return
                    sSeq = GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
                    iBarcode_matched = 1
                    sQuery_seq_after_barcode = seq after end index of barcode from FASTQ
                    lQuery_qual_after_barcode = [spliced Quality Score from end index of barcode]
                """
                (sSeq, iBarcode_matched, sQuery_seq_after_barcode, lQuery_qual_after_barcode) = \
                    self._CheckBarcodePosAndRemove(sSeq, sBarcode, iBarcode_matched, lQual)

                ## Alignment Seq to Ref
                """
                npGapIncentive = np.zeros(len(sRef_seq_after_barcode) + 1, dtype=np.int)
                numpy zero matrix
                """
                npGapIncentive = InstGotoh.GapIncentive(sRef_seq_after_barcode)

                try:
                    """
                    DIFF CHECK by RunCRISPResso2.CRISPResso2Align.global_align
                    :param
                        sQuery_seq_after_barcode = seq after end index of barcode from FASTQ
                        sRef_seq_after_barcode = seq after end index of barcode from REFERENCE
                    :return
                    """
                    # TODO it's guessing of lResult
                    #  sQuery_needle_ori = lResult[0] = GCATACACCGTACTATCACAGTGTCTACACT...
                    #  sRef_needle_ori   = lResult[1] = GCATACACCGTACTATCACAGTGTCTACACT...
                    lResult = InstGotoh.RunCRISPResso2(sQuery_seq_after_barcode.upper(),
                                                       sRef_seq_after_barcode.upper(),
                                                       npGapIncentive)
                except Exception as e:
                    logging.error(e, exc_info=True)
                    continue

                sQuery_needle_ori = lResult[0]
                sRef_needle_ori   = lResult[1]

                """
                # e.g.    ref   ------AAAGGCTACGATCTGCG------
                #         query AAAAAAAAATCGCTCTCGCTCTCCGATCT
                # trimmed ref         AAAGGCTACGATCTGCG         = sRef_needle
                # trimmed qeury       AAATCGCTCTCGCTCTC         = sQuery_needle
                """
                sRef_needle, sQuery_needle            = self._TrimRedundantSideAlignment(sRef_needle_ori, sQuery_needle_ori)
                """
                lInsertion_in_read = [[insertion seq index, counts], [100, 1], [119, 13]]
                lDeletion_in_read = [[deletion seq index, counts], [97, 1], [102, 3]]
                """
                lInsertion_in_read, lDeletion_in_read = self._MakeIndelPosInfo(sRef_needle, sQuery_needle)

                # print 'sQuery_needle', sQuery_needle
                # print 'lInsertion_in_read: onebase', lInsertion_in_read
                # print 'lDeletion_in_read: onebase', lDeletion_in_read
                # print 'i5bp_front_Indel_end', i5bp_front_Indel_end
                # print 'iIndel_end_from_barcode_pos', iIndel_end_from_barcode_pos

                lTarget_indel_result = []  # ['20M2I', '23M3D' ...]
                """
                :param
                    lInsertion_in_read = [[insertion seq index, counts], [100, 1], [119, 13]]
                    iKbp_front_Indel_end = iIndel_end_from_barcode_pos - 6  ## cas9:-6, cpf1:-4
                                            cleavege point(index) from end of target_region in sRef_seq WOUT BARCD SEQ
                    lTarget_indel_result = []
                    iIndel_end_from_barcode_pos = iIndel_end_next_pos_from_barcode_end  = end of target_region in sRef_seq WOUT BARCD SEQ
                    iInsert_count = 0 
                """
                iInsert_count = self._TakeInsertionFromAlignment(lInsertion_in_read, iKbp_front_Indel_end, lTarget_indel_result,
                                                                 iIndel_end_from_barcode_pos, iInsert_count)

                iDelete_count = self._TakeDeletionFromAlignment(lDeletion_in_read, iKbp_front_Indel_end, lTarget_indel_result,
                                                                iIndel_end_from_barcode_pos, iDelete_count)

                if iInsert_count == 1 and iDelete_count == 1:
                    iComplex_count = 1
                    iInsert_count = 0
                    iDelete_count = 0

                # """ test set
                # print 'sBarcode', sBarcode
                # print 'sTarget_region', sTarget_region
                # print 'sRef_seq_after_barcode', sRef_seq_after_barcode
                # print 'sSeq_after_barcode', sQuery_seq
                # print 'iIndel_start_from_barcode_pos', iIndel_start_from_barcode_pos
                # print 'iIndel_end_from_barcode_pos', iIndel_end_from_barcode_pos
                # """
                """
                listResultFASTQ = [sName, sSeq, '+', ''.join(chr(i + 33) for i in lQual)]
                        ex) [Sequence identifier,  Nucleotide sequence from FASTQ, '+' , Quality scores ]
                dResult[sBarcode][self.intTotalFastq].append(listResultFASTQ)
                """
                listResultFASTQ = self._MakeAndStoreQuality(sName, sSeq, lQual, dResult, sBarcode)

                """
                iQual_end_pos + 1 is not correct, because the position is like this.
                *NNNN*(N)
                So, '+ 1' is removed.
                Howerver, seqeunce inspects until (N) position. indel is detected front of *(N).
                """
                ################################################################
                #print(lTarget_indel_result)
                #set_trace()
                # len(sQuery_seq_after_barcode) == len(lQuery_qual_after_barcode)
                """
                Quality Score 
                self.intQualCutoff = default = 20
                """
                if np.mean(lQuery_qual_after_barcode[iIndel_start_from_barcode_pos : iIndel_end_from_barcode_pos + 1]) >= self.intQualCutoff: ## Quality cutoff

                    """
                    23M3I
                    23M is included junk_seq after barcode,

                    barcorde  junk   targetseq   others
                    *********ACCCT-------------ACACACACC
                    so should select target region.
                    If junk seq is removed by target region seq index pos.
                    """
                    # filter start,
                    iTarget_start_from_barcode   = sRef_seq_after_barcode.index(sTarget_region)
                    """
                    :param 
                        lTarget_indel_result = ['20M2I', '23M3D' ...]
                        iTarget_start_from_barcode = sRef_seq_after_barcode.index(sTarget_region)
                    :return 
                        lTrimmed_target_indel_result =  ['20M2I', '23M3D' ...] after filtering out
                    """
                    lTrimmed_target_indel_result = self._FixPos(lTarget_indel_result, iTarget_start_from_barcode)

                    # print 'Check'
                    # print sRef_seq_after_barcode
                    # print sQuery_seq_after_barcode
                    # print lTrimmed_target_indel_result
                    # print('Trimmed', lTrimmed_target_indel_result)

                    sRef_seq_after_barcode, sQuery_seq_after_barcode = self._StoreToDictResult(sRef_seq_after_barcode, sQuery_seq_after_barcode, iTarget_start_from_barcode,
                                                                       dResult, sBarcode, lTrimmed_target_indel_result, sTarget_region, sRef_needle_ori,
                                                                       sQuery_needle_ori, iInsert_count, iDelete_count, iComplex_count, listResultFASTQ)
                else:
                    iInsert_count  = 0
                    iDelete_count  = 0
                    iComplex_count = 0

                # total matched reads, insertion, deletion, complex
                dResult[sBarcode][self.intNumOfTotal] += iBarcode_matched
                dResult[sBarcode][self.intNumOfIns] += iInsert_count
                dResult[sBarcode][self.intNumOfDel] += iDelete_count
                dResult[sBarcode][self.intNumofCom] += iComplex_count

                iBarcode_matched = 0
                iInsert_count    = 0
                iDelete_count    = 0
                iComplex_count   = 0

            #End:for
        #END:for
        return dResult
    """
    sSeq = GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
    sBarcode = strSeqWindow
    iBarcode_matched = 0 (value for initial)
    lQual =  [37,32,37,37,37,37,37,37 insted of FAFFFFFF...
    """
    def _CheckBarcodePosAndRemove(self, sSeq, sBarcode, iBarcode_matched, lQual):

        # Check the barcode pos and remove it.
        sSeq = sSeq.replace('\r', '')
        iBarcode_start_pos_FASTQ = sSeq.index(sBarcode)
        iBarcode_matched += 1
        iBarcode_end_pos_FASTQ = iBarcode_start_pos_FASTQ + len(sBarcode) - 1

        """
            junk seq  target region
        ref: AGGAG    AGAGAGAGAGA
        que: AGGAG    AGAGAGAGAGA
        But, It doesnt know where is the target region because of existed indels.
        So, There is no way not to include it.
        """
        # Use this.
        sQuery_seq_after_barcode = sSeq[iBarcode_end_pos_FASTQ + 1:]
        lQuery_qual_after_barcode = lQual[iBarcode_end_pos_FASTQ:]

        return (sSeq, iBarcode_matched, sQuery_seq_after_barcode, lQuery_qual_after_barcode)
    """
    :return
        sSeq = GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
        iBarcode_matched = 1
        sQuery_seq_after_barcode = seq after end index of barcode from FASTQ
        lQuery_qual_after_barcode = [spliced Quality Score from end index of barcode]
    """

    def _TrimRedundantSideAlignment(self, sRef_needle_ori, sQuery_needle_ori):

        # detach forward ---, backward ---
        # e.g.    ref   ------AAAGGCTACGATCTGCG------
        #         query AAAAAAAAATCGCTCTCGCTCTCCGATCT
        # trimmed ref         AAAGGCTACGATCTGCG
        # trimmed qeury       AAATCGCTCTCGCTCTC
        # TODO really trimmed like those???????? especially sQuery_needle = trimmed qeury
        iReal_ref_needle_start = 0
        iReal_ref_needle_end = len(sRef_needle_ori)
        iRef_needle_len = len(sRef_needle_ori)

        for i, sRef_nucle in enumerate(sRef_needle_ori):
            if sRef_nucle in ['A', 'C', 'G', 'T']:
                iReal_ref_needle_start = i
                break

        for i, sRef_nucle in enumerate(sRef_needle_ori[::-1]):
            if sRef_nucle in ['A', 'C', 'G', 'T']:
                iReal_ref_needle_end = iRef_needle_len - (i + 1)
                # forward 0 1 2  len : 3
                # reverse 2 1 0,  len - (2 + 1) = 0
                break

        sRef_needle = sRef_needle_ori[iReal_ref_needle_start:iReal_ref_needle_end + 1]
        # TODO if iReal_ref_needle_start == 0:????????????????????
        if iReal_ref_needle_start:
            sQuery_needle = sQuery_needle_ori[:iReal_ref_needle_end]
        sQuery_needle = sQuery_needle_ori[:len(sRef_needle)]
        # detaching completion
        return (sRef_needle, sQuery_needle)

    """
    # e.g.    ref   ------AAAGGCTACGATCTGCG------
    #         query AAAAAAAAATCGCTCTCGCTCTCCGATCT
    # trimmed ref         AAAGGCTACGATCTGCG         = sRef_needle
    # trimmed qeury       AAATCGCTCTCGCTCTC         = sQuery_needle
    '-' in ref is insertion
    '-' in FASTQ is deletion
    """
    def _MakeIndelPosInfo(self, sRef_needle, sQuery_needle):

        # indel info making.
        iNeedle_match_pos_ref   = 0
        iNeedle_match_pos_query = 0
        iNeedle_insertion       = 0
        iNeedle_deletion        = 0

        lInsertion_in_read = []  # insertion result [[insertion seq index, counts], [100, 1], [119, 13]]
        lDeletion_in_read  = []  # [[deletion seq index, counts], [97, 1], [102, 3]]

        # print 'sRef_needle', sRef_needle
        # print 'sQuery_needle', sQuery_needle
        # TODO guessing (sRef_nucle, sQuery_nucle) = [('A','C'),('-','T'),('-','G'),('G','-') ...]
        for i, (sRef_nucle, sQuery_nucle) in enumerate(zip(sRef_needle, sQuery_needle)):
            """
            zip(seq1 [, seq2 [...]]) -> [(seq1[0], seq2[0] ...), (...)]

            Return a list of tuples, where each tuple contains the i-th element
            from each of the argument sequences.  The returned list is truncated
            in length to the length of the shortest argument sequence.
            """

            if sRef_nucle == '-':
                iNeedle_insertion += 1

            if sQuery_nucle == '-':
                iNeedle_deletion += 1

            if sRef_nucle in ['A', 'C', 'G', 'T']:
                if iNeedle_insertion:
                    lInsertion_in_read.append([iNeedle_match_pos_ref, iNeedle_insertion])
                    iNeedle_insertion = 0
                iNeedle_match_pos_ref += 1

            if sQuery_nucle in ['A', 'C', 'G', 'T']:
                if iNeedle_deletion:
                    lDeletion_in_read.append([iNeedle_match_pos_query, iNeedle_deletion])
                    iNeedle_match_pos_query += iNeedle_deletion
                    iNeedle_deletion = 0
                iNeedle_match_pos_query += 1
                # print 'sRef_needle', sRef_needle

        return (lInsertion_in_read, lDeletion_in_read)

    """
    :param
        lInsertion_in_read = [[insertion seq index, counts], [100, 1], [119, 13]]
        iKbp_front_Indel_end = iIndel_end_from_barcode_pos - 6  ## cas9:-6, cpf1:-4
                                cleavege point(index) from end of target_region in sRef_seq WOUT BARCD SEQ
        lTarget_indel_result = []
        iIndel_end_from_barcode_pos = iIndel_end_next_pos_from_barcode_end  = end of target_region in sRef_seq WOUT BARCD SEQ
        iInsert_count = 0 
    """
    def _TakeInsertionFromAlignment(self, lInsertion_in_read, iKbp_front_Indel_end, lTarget_indel_result,
                                    iIndel_end_from_barcode_pos, iInsert_count):
        """
        ins case
        ...............................NNNNNNNNNNNNNN....NNNNNNNNNNNNNNNNNNN*NNNNNAGCTT
        """
        for iMatch_pos, iInsertion_pos in lInsertion_in_read:  # lInsertion_in_read = [[insertion seq index, counts], [100, 1], [119, 13]]
            """
            iMatch_pos = insertion seq index
            iInsertion_pos = counts
            """
            if self.strPamType == 'CAS9':
                # if i5bp_front_Indel_end == iMatch_pos -1 or iIndel_end_from_barcode_pos == iMatch_pos -1: # iMatch_pos is one base # original ver
                if iKbp_front_Indel_end - self.intInsertionWin <= iMatch_pos - 1 <= iKbp_front_Indel_end + self.intInsertionWin:  # iMatch_pos is one base
                    iInsert_count = 1
                    lTarget_indel_result.append(str(iMatch_pos) + 'M' + str(iInsertion_pos) + 'I')

            elif self.strPamType == 'CPF1':
                if iKbp_front_Indel_end - self.intInsertionWin <= iMatch_pos - 1 <= iKbp_front_Indel_end + self.intInsertionWin or \
                        iIndel_end_from_barcode_pos - self.intInsertionWin <= iMatch_pos - 1 <= iIndel_end_from_barcode_pos + self.intInsertionWin:  # iMatch_pos is one base
                    iInsert_count = 1
                    lTarget_indel_result.append(str(iMatch_pos) + 'M' + str(iInsertion_pos) + 'I')

        return iInsert_count

    def _TakeDeletionFromAlignment(self, lDeletion_in_read, iKbp_front_Indel_end, lTarget_indel_result,
                                   iIndel_end_from_barcode_pos, iDelete_count):

        """
        del case 1
        ...............................NNNNNNNNNNNNNN....NNNNNNNNNNNNNNNNNNNNN**NNNAGCTT
        del case 2
        ...............................NNNNNNNNNNNNNN....NNNNNNNNNNNNNNNNNNNNN**NNNNNCTT
        """
        for iMatch_pos, iDeletion_pos in lDeletion_in_read:
            """
            Insertion: 30M3I
                   ^
            ACGT---ACGT
            ACGTTTTACGT -> check this seq
            Insertion just check two position

            Deletion: 30M3D
                 ^
            ACGTTTTACGT
            ACGT---ACGT -> check this seq
            But deletion has to includes overlap deletion.
            """
            if self.strPamType == 'CAS9':
                if (iMatch_pos - self.intDeletionWin - 1 <= iKbp_front_Indel_end and iKbp_front_Indel_end < (iMatch_pos + iDeletion_pos + self.intDeletionWin - 1)):
                    iDelete_count = 1
                    lTarget_indel_result.append(str(iMatch_pos) + 'M' + str(iDeletion_pos) + 'D')
            elif self.strPamType == 'CPF1':
                if (iMatch_pos - self.intDeletionWin - 1 <= iKbp_front_Indel_end and iKbp_front_Indel_end < (iMatch_pos + iDeletion_pos + self.intDeletionWin - 1)) or \
                   (iMatch_pos - self.intDeletionWin - 1 <= iIndel_end_from_barcode_pos and iIndel_end_from_barcode_pos < (iMatch_pos + iDeletion_pos + self.intDeletionWin - 1)):
                    iDelete_count = 1
                    lTarget_indel_result.append(str(iMatch_pos) + 'M' + str(iDeletion_pos) + 'D')

        return iDelete_count

    def _MakeAndStoreQuality(self, sName, sSeq, lQual, dResult, sBarcode):
        listResultFASTQ = [sName, sSeq, '+', ''.join(chr(i + 33) for i in lQual)]
        dResult[sBarcode][self.intTotalFastq].append(listResultFASTQ)
        return listResultFASTQ

    """
    :param 
        lTarget_indel_result = ['20M2I', '23M3D' ...]
        iTarget_start_from_barcode = sRef_seq_after_barcode.index(sTarget_region)
    """
    def _FixPos(self, lTarget_indel_result, iTarget_start_from_barcode):

        lTrimmed_target_indel_result = []

        for sINDEL in lTarget_indel_result:
            """
            sINDEL = '20M2I'
            iMatch_target_start = start index of INDEL in Target_region 
            """
            # B - A is not included B position, so +1
            iMatch_target_start = int(sINDEL.split('M')[0]) - iTarget_start_from_barcode
            """ This part determines a deletion range.
                                      ^ current match pos                                           
            AGCTACGATCAGCATCTGACTTACTTC[barcode]


                           ^ fix the match start at here. (target region)                                           
            AGCTACGATCAGCATC TGACTTACTTC[barcode]

            if iMatch_target_start < 0:
                sContinue = 1

            But, this method has some problems.

                           ^ barcode start
            AGCTACGATCAGCAT*********C[barcode]
            Like this pattern doesn't seleted. because, deletion checking is begun the target region start position. 
            Thus, I have fixed this problem.
            """
            # TODO -(iTarget_start_from_barcode) is needed - ?????
            if iMatch_target_start <= -(iTarget_start_from_barcode):
                # print(iMatch_target_start, iTarget_start_from_barcode)
                continue

            lTrimmed_target_indel_result.append(str(iMatch_target_start) + 'M' + sINDEL.split('M')[1])
        # filter end
        return lTrimmed_target_indel_result

    def _StoreToDictResult(self, sRef_seq_after_barcode, sQuery_seq_after_barcode, iTarget_start_from_barcode,
                           dResult, sBarcode, lTrimmed_target_indel_result, sTarget_region, sRef_needle_ori, sQuery_needle_ori,
                           iInsert_count, iDelete_count, iComplex_count, listResultFASTQ):

        sRef_seq_after_barcode   = sRef_seq_after_barcode[iTarget_start_from_barcode:]
        sQuery_seq_after_barcode = sQuery_seq_after_barcode[iTarget_start_from_barcode:]

        dResult[sBarcode][self.intIndelInfo].append([sRef_seq_after_barcode, sQuery_seq_after_barcode, lTrimmed_target_indel_result,
                                                     sTarget_region, sRef_needle_ori, sQuery_needle_ori])
        if iInsert_count:
            dResult[sBarcode][self.intInsFastq].append(listResultFASTQ)
        elif iDelete_count:
            dResult[sBarcode][self.intDelFastq].append(listResultFASTQ)
        elif iComplex_count:
            dResult[sBarcode][self.intComFastq].append(listResultFASTQ)

        return (sRef_seq_after_barcode, sQuery_seq_after_barcode)

    """
    dResult = { sBarcode : { self.intIndelInfo  = 8 : [[sRef_seq_after_barcode, sQuery_seq_after_barcode, lTarget_indel_result, sTarget_region], ..]) 
                        , self.intTotalFastq : [Sequence identifier,  Nucleotide sequence from FASTQ, '+' , Quality scores ] 
                        , self.intNumOfTotal : iBarcode_matched 
                        , self.intNumOfIns : iInsert_count 
                        , self.intNumOfDel : iDelete_count 
                        , self.intNumofCom : iComplex_count
                         }
     , ...}
    """
    def CalculateIndelFrequency(self, dResult):
        dResult_INDEL_freq = {}
        """
         lValue = { self.intIndelInfo  = 8 : [[sRef_seq_after_barcode, sQuery_seq_after_barcode, lTarget_indel_result, sTarget_region], ..]) 
                    , self.intTotalFastq = 4 : [Sequence identifier,  Nucleotide sequence from FASTQ, '+' , Quality scores ] 
                    , self.intNumOfTotal = 0 : iBarcode_matched 
                    , self.intNumOfIns = 1 : iInsert_count 
                    , self.intNumOfDel = 2 : iDelete_count 
                    , self.intNumofCom = 3 : iComplex_count
                     }
        """
        for sBarcode, lValue in dResult.items():  # lValue[gINDEL_info] : [[sRef_seq_after_barcode, sQuery_seq_after_barcode, lTarget_indel_result, sTarget_region], ..])
            sRef_seq_loop = ''
            llINDEL_store = []  # ['ACAGACAGA', ['20M2I', '23M3D']]
            dINDEL_freq   = {}

            if lValue[self.intIndelInfo]:
                """
                lValue[self.intIndelInfo] = [
                            sRef_seq_loop = sRef_seq_after_barcode
                            , sQuery_seq = sQuery_seq_after_barcode
                            , lINDEL = lTarget_indel_result ... [['20M2I', '23M3D'], ...] 
                            , sTarget_region = 
                            , sRef_needle = 
                            , sQuery_needle = 
                            ]
                """
                for sRef_seq_loop, sQuery_seq, lINDEL, sTarget_region, sRef_needle, sQuery_needle in lValue[self.intIndelInfo]: # llINDEL : [['20M2I', '23M3D'], ...]
                    # print 'lINDEL', lINDEL
                    for sINDEL in lINDEL:
                        llINDEL_store.append([sQuery_seq, sINDEL, sRef_needle, sQuery_needle])

                iTotal = len([lINDEL for sQuery_seq, lINDEL, sRef_needle, sQuery_needle in llINDEL_store])

                for sQuery_seq, sINDEL, sRef_needle, sQuery_needle in llINDEL_store:
                    dINDEL_freq[sINDEL] = [[], 0, [], []]

                for sQuery_seq, sINDEL, sRef_needle, sQuery_needle in llINDEL_store:
                    dINDEL_freq[sINDEL][1] += 1
                    dINDEL_freq[sINDEL][0].append(sQuery_seq)
                    dINDEL_freq[sINDEL][2].append(sRef_needle)
                    dINDEL_freq[sINDEL][3].append(sQuery_needle)

                for sINDEL in dINDEL_freq:
                    lQuery        = dINDEL_freq[sINDEL][0]
                    iFreq         = dINDEL_freq[sINDEL][1]
                    lRef_needle   = dINDEL_freq[sINDEL][2]
                    lQuery_needle = dINDEL_freq[sINDEL][3]

                    try:
                        dResult_INDEL_freq[sBarcode].append([sRef_seq_loop, lQuery, sINDEL, float(iFreq) / iTotal,
                                                             sTarget_region, lRef_needle, lQuery_needle])
                    except (KeyError, TypeError, AttributeError) as e:
                        dResult_INDEL_freq[sBarcode] = []
                        dResult_INDEL_freq[sBarcode].append([sRef_seq_loop, lQuery, sINDEL, float(iFreq) / iTotal,
                                                             sTarget_region, lRef_needle, lQuery_needle])
            # end: if lValue[gINDEL_info]
        # end: for sBarcode, lValue
        return dResult_INDEL_freq
        # end1: return
    # end: def
#END:class


class clsOutputMaker(object):

    def __init__(self, InstParameter):

        self.strOutputdir     = InstParameter.strOutputdir
        self.strForwardFqPath = InstParameter.strForwardFqPath

    def MakePickleOutput(self, dictResult, dictResultIndelFreq, strBarcodePamPos=''):

        dictOutput = {'dictResult': dictResult,
                      'dictResultIndelFreq': dictResultIndelFreq,
                      'strBarcodePamPos': strBarcodePamPos}

        with open('{outdir}/Tmp/Pickle/{fq}.pickle'.format(outdir=self.strOutputdir, fq=os.path.basename(self.strForwardFqPath)), 'wb') as Pickle:
            pickle.dump(dictOutput, Pickle)


def Main():

    InstParameter = clsParameter()
    logging.basicConfig(format='%(process)d %(levelname)s %(asctime)s : %(message)s',
                        level=logging.DEBUG,
                        filename=InstParameter.strLogPath,
                        filemode='a')

    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    logging.info('Program start : %s' % InstParameter.strForwardFqPath)

    logging.info('File Open')
    InstFileOpen     = clsFastqOpener(InstParameter)
    """
    listFastqForward = [(Sequence identifier,Nucleotide sequence, Quality scores array),(seq, qual)]
        ex) (@MN00416:88:000H2WVH3:1:11101:17048:1168 1:N:0:1
            , GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
            , [37,32,37,37,37,37,37,37 insted of FAFFFFFF...
            )
    """
    listFastqForward = InstFileOpen.OpenFastqForward()
    if InstParameter.strPair == 'True':
        listFastqReverse = InstFileOpen.OpenFastqReverse()

    InstIndelSearch = clsIndelSearchParser(InstParameter)

    InstOutput = clsOutputMaker(InstParameter)

    if InstParameter.strPamType == 'CPF1':
        logging.info('Search barcode INDEL pos')
        dRef, dResult = InstIndelSearch.SearchBarcodeIndelPosition(InstParameter.strBarcodePamPos)  # ref check.

        logging.info('Search INDEL forward')
        dResultForward = InstIndelSearch.SearchIndel(listFastqForward, dRef, dResult)

        if InstParameter.strPair == 'True':
            logging.info('Search INDEL reverse')
            dResultReverse = InstIndelSearch.SearchIndel(listFastqReverse, dRef, dResultForward)

            logging.info('Calculate INDEL frequency')
            dictResultIndelFreq = InstIndelSearch.CalculateIndelFrequency(dResultReverse)

            logging.info('Make pickle output forward')
            InstOutput.MakePickleOutput(dResultReverse, dictResultIndelFreq)

        else:
            logging.info('Calculate INDEL frequency')
            dictResultIndelFreq = InstIndelSearch.CalculateIndelFrequency(dResultForward)

            logging.info('Make pickle output forward')
            InstOutput.MakePickleOutput(dResultForward, dictResultIndelFreq)

    elif InstParameter.strPamType == 'CAS9':
        """
        InstParameter.strBarcodePamPos is ... PAM position: Forward Reverse
        """
        logging.info('Search barcode INDEL pos')
        """
        dRef[sBarcode] = (sRef_seq, sTarget_region, sRef_seq_after_barcode, iIndel_start_next_pos_from_barcode_end,
                          iIndel_end_next_pos_from_barcode_end, iIndel_start_pos, iIndel_end_pos)  
                          # total matched reads, insertion, deletion, complex
        # lRef   : [(ref_seq, ref_seq_after_barcode, barcode, barcode end pos, indel end pos, indel from barcode),(...)]

        ## iIndel_start_next_pos_from_barcode_end = start index of target region in sRef_seq WOUT BARCD SEQ 
        ## iIndel_end_next_pos_from_barcode_end = end index of target region in sRef_seq WOUT BARCD SEQ
        ## iIndel_start_pos ... start index of sTarget_region in sRef_seq
        ## iIndel_end_pos ... end index of sTarget_region in sRef_seq

        dResult[sBarcode] = [0, 0, 0, 0, [], [], [], [], []]
        # dResult = [# of total, # of ins, # of del, # of com, [total FASTQ], [ins FASTQ], [del FASTQ], [com FASTQ]]
        """
        dRef, dResult   = InstIndelSearch.SearchBarcodeIndelPosition(InstParameter.strBarcodePamPos)
        logging.info('Search INDEL')

        """
        :param
            listFastqForward = [(Sequence identifier,Nucleotide sequence, Quality scores array),(seq, qual)]
                ex) (@MN00416:88:000H2WVH3:1:11101:17048:1168 1:N:0:1
                    , GAATCTACTTAAACAAGGCAAAATGCCGTGTTTATCTCGTCAACTTGTTGGCGAGATTTTTTGCATACACCGTACTATCACAGTGTCTACACTCTGCCTGAACAGAACTTGGGAATCACTGAGCGCAGCTTGGCGTAACTAGATCTCTACTCTACCACTTGTACTTCAGCGG
                    , [37,32,37,37,37,37,37,37 insted of FAFFFFFF...
                    )
            InstParameter.strBarcodePamPos is ... PAM position: Forward Reverse
        :return
            dResult_forward = { sBarcode : { self.intIndelInfo  = 8 : [[sRef_seq_after_barcode, sQuery_seq_after_barcode, lTarget_indel_result, sTarget_region], ..]) 
                                    , self.intTotalFastq = 4 : [Sequence identifier,  Nucleotide sequence from FASTQ, '+' , Quality scores ] 
                                    , self.intNumOfTotal = 0 : iBarcode_matched 
                                    , self.intNumOfIns = 1 : iInsert_count 
                                    , self.intNumOfDel = 2 : iDelete_count 
                                    , self.intNumofCom = 3 : iComplex_count
                                     }
             , ...}
        """
        dResult_forward = InstIndelSearch.SearchIndel(listFastqForward, dRef, dResult, InstParameter.strBarcodePamPos)

        logging.info('Calculate INDEL frequency')
        """
        dResult_INDEL_freq = { sBarcode : [sRef_seq_loop = sRef_seq_after_barcode
                                            , lQuery = sQuery_seq_after_barcode
                                            , sINDEL = lTarget_indel_result ... [['20M2I', '23M3D'], ...]
                                            , float(iFreq) / iTotal
                                            , sTarget_region
                                            , lRef_needle
                                            , lQuery_needle]
                                }
        """
        dResult_INDEL_freq = InstIndelSearch.CalculateIndelFrequency(dResult_forward)

        logging.info('Make pickle output forward')
        """
        store data as each instance like python object by pickle ... so open file as byte 'wb','rb'
        """
        InstOutput.MakePickleOutput(dResult_forward, dResult_INDEL_freq, InstParameter.strBarcodePamPos)

    logging.info('Program end : %s' % InstParameter.strForwardFqPath)
#END:def


if __name__ == '__main__':
    Main()


