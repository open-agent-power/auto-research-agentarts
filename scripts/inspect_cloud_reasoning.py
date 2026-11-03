"""Inspect the pinned model's high reasoning and free account; never infer."""
import argparse
import json
import os
from pathlib import Path

from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import file_info, parse_json, require
from autoresearch.reasoning_profile import OwnedHighReasoningOllama, code_identity


class MetadataOnlyOllama(OwnedHighReasoningOllama):
    def _chat(self,*args,**kwargs):
        raise ResearchError('METADATA_ONLY','Chat is forbidden in metadata inspection.')
    def _wire(self,route,*args,**kwargs):
        require(route!='/api/chat','METADATA_ONLY','Chat route is forbidden in metadata inspection.')
        return super()._wire(route,*args,**kwargs)


def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--model-store',required=True)
    parser.add_argument('--port',type=int,default=11448)
    parser.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args=parser.parse_args();output=Path(args.output).absolute();store=Path(args.model_store).absolute()
    for path in (output,*output.parents):
        require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'UNSAFE_PATH','Inspection output cannot redirect.')
    require(not(output==store or output.is_relative_to(store) or store.is_relative_to(output)),'UNSAFE_PATH','Inspection output must be separate from model store.')
    output.mkdir(parents=True,exist_ok=False);server=None
    try:
        with MetadataOnlyOllama(args.ollama_executable,output/'model-cache',output/'transport',port=args.port,model_store=store) as server:
            identity=server.acquire()
            _,_,raw=file_info(server.output/'account-acquired.json',100_000)
            write(output/'result.json',{'ok':True,'identity':identity,'capabilities':server.reasoning_capabilities,
                                      'account':parse_json(raw),'profile_code_sha256':code_identity(),
                                      'model_calls':0,'configured_budget':False})
        write(output/'cleanup.json',{'owned_server_stopped':server.stopped,'key_metadata_unchanged':server.key_metadata_unchanged})
        print(json.dumps({'ok':True,'model_calls':0,'high_advertised':True,'owned_server_stopped':server.stopped}));return 0
    except (ResearchError,OSError,ValueError) as error:
        receipt={'ok':False,'code':getattr(error,'code','REASONING_METADATA_FAILED'),'error_class':type(error).__name__,'model_calls':0,
                 'owned_server_stopped':getattr(server,'stopped',False),'key_metadata_unchanged':getattr(server,'key_metadata_unchanged',None)}
        write(output/'failure.json',receipt);print(json.dumps(receipt));return 1


if __name__=='__main__':raise SystemExit(main())
