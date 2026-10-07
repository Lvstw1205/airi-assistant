import json
from pathlib import Path
from typing import Literal
import threading
import yaml
from pydantic import BaseModel,ConfigDict,Field,model_validator

AGENTS={'ceo','research','coding','data_analyst','finance','stock101','news','youtube','secretary','memory_manager','critic','system_health'}

class Agent(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    agent_id:str
    name:str
    role:str
    description:str
    system_prompt_file:str
    capabilities:list[str]
    tools:list[str]
    allowed_models:list[str]
    preferred_node:Literal['prime','works']='prime'
    priority:int=Field(default=50,ge=0,le=100)
    memory_namespace:str
    max_context_tokens:int=Field(default=8192,ge=1024,le=16000)
    timeout_seconds:int=Field(default=120,ge=1,le=300)
    approval_ceiling:Literal['READ_ONLY','LOW_RISK_WRITE','CONFIRM_REQUIRED']
    critic_required:bool=True
    enabled:bool=True

class Registry:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.RLock();self.agents={};self.prompts={};self.reload()
    def reload(self):
        candidates={};prompts={}
        for path in sorted((self.root/'config/agents').glob('*.yaml')):
            agent=Agent.model_validate(yaml.safe_load(path.read_text()))
            if agent.agent_id not in AGENTS or agent.agent_id in candidates:raise ValueError('Unknown or duplicate agent')
            source=(self.root/agent.system_prompt_file).resolve()
            if not source.is_relative_to((self.root/'prompts/agents').resolve()):raise ValueError('Prompt outside allowed folder')
            prompts[agent.agent_id]=source.read_text();candidates[agent.agent_id]=agent
        if set(candidates)!=AGENTS:raise ValueError('Agent registry is incomplete')
        with self.lock:self.agents,self.prompts=candidates,prompts
        return len(candidates)

class Subtask(BaseModel):
    model_config=ConfigDict(extra='forbid')
    key:str=Field(pattern=r'^[a-z][a-z0-9_]{0,39}$')
    agent_id:str
    objective:str=Field(min_length=1,max_length=2000)
    inputs:dict=Field(default_factory=dict)
    depends_on:list[str]=Field(default_factory=list)
    optional:bool=False
    node_hint:Literal['prime','works','any']='prime'
    deadline_seconds:int=Field(default=120,ge=1,le=300)

class Plan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    goal:str=Field(min_length=1,max_length=2000)
    user_language:Literal['ko','en']='ko'
    needs_fresh_data:bool=True
    subtasks:list[Subtask]=Field(min_length=1,max_length=8)
    critic_required:bool=True
    max_total_seconds:int=Field(default=300,ge=1,le=900)
    @model_validator(mode='after')
    def dag(self):
        by_key={t.key:t for t in self.subtasks}
        if len(by_key)!=len(self.subtasks):raise ValueError('Duplicate task keys')
        visiting=set();depths={}
        def depth(key):
            if key in visiting:raise ValueError('Cycle in plan')
            if key not in by_key:raise ValueError('Unknown dependency')
            if key in depths:return depths[key]
            task=by_key[key]
            if task.agent_id not in AGENTS:raise ValueError('Unknown agent')
            visiting.add(key);n=1+max((depth(x) for x in task.depends_on),default=0);visiting.remove(key)
            if n>3:raise ValueError('Plan depth exceeds 3')
            depths[key]=n;return n
        for key in by_key:depth(key)
        return self

def financial_plan(query,symbol='NVDA'):
    specs=[('news','news',[],{'query':symbol+' latest company news'}),('finance','finance',[],{'symbol':symbol}),
           ('stock','stock101',[],{'symbol':symbol}),('memory','memory_manager',[],{'query':symbol}),
           ('review','critic',['news','finance','stock','memory'],{}),('answer','ceo',['review'],{'symbol':symbol})]
    return Plan(goal=query,subtasks=[Subtask(key=k,agent_id=a,objective=query,inputs=i,depends_on=d,optional=a in ('critic','ceo')) for k,a,d,i in specs])
